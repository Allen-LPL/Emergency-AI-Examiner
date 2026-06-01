import json
import random
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response, StreamingResponse
from loguru import logger
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import get_async_db
from backend.app.schemas.cpr_metrics import (
    CprMetricsResponse,
    CprMetricsUpload,
    derive_scoring_metrics,
)
from backend.app.schemas.event import TimelineResponse
from backend.app.schemas.exam import (
    ExamListResponse,
    ExamStatusResponse,
    ExamUploadResponse,
)
from backend.app.schemas.score import ScoreResultResponse
from backend.app.services import exam_service
from backend.app.tasks.exam_task import process_exam_task

router = APIRouter(prefix="/exam", tags=["考试"])

# 允许上传的视频文件扩展名
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

# 视频文件扩展名 → Content-Type 映射 (H5 <video> 播放接口使用)
VIDEO_CONTENT_TYPE_MAP = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}

# 视频流式播放分块大小 (64KB) - 兼顾 TCP 段大小与内存占用
_VIDEO_STREAM_CHUNK = 64 * 1024

# 上传接口 device_code 缺省值 - 当前业务为单池设备直连, 未携带设备码时统一归入此默认值
DEFAULT_UPLOAD_DEVICE_CODE = "8888888"

# 满分 mock 指标 - 客观评分 40/40
PERFECT_MOCK_METRICS = {
    "session_duration_sec": 180.0,
    "compression_duration_sec": 150.0,
    "press_total": 200,
    "press_correct": 190,
    "press_wrong": 10,
    "press_frequency": 110.0,
    "press_avg_depth": 52.0,
    "blow_total": 20,
    "blow_correct": 19,
    "blow_wrong": 1,
    "blow_avg_volume": 540.0,
    "shoulder_tapped": True,
}


@router.post("/upload", response_model=ExamUploadResponse)
async def upload_exam(
    file: UploadFile = File(..., description="考试视频文件"),
    device_code: str = Form(
        default=DEFAULT_UPLOAD_DEVICE_CODE,
        min_length=1,
        max_length=64,
        description=f"设备唯一码, 未传时默认 {DEFAULT_UPLOAD_DEVICE_CODE}",
    ),
    metrics: str | None = Form(default=None, description="CPR 模拟人指标 JSON 字符串"),
    db: AsyncSession = Depends(get_async_db),
):
    """合并上传接口 - 视频文件 + 设备码 + CPR 指标(可选)一次性上报。"""
    # 校验文件扩展名
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}, 支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 解析 metrics(若提供)
    metrics_payload: CprMetricsUpload | None = None
    if metrics is not None and metrics.strip():
        try:
            metrics_dict = json.loads(metrics)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"metrics 字段非合法 JSON: {exc}",
            )
        try:
            metrics_payload = CprMetricsUpload(**metrics_dict)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"metrics 字段校验失败: {exc.errors()}",
            )

    # 准备上传目录 (绝对路径, api/celery_worker 共享挂载)
    upload_dir = Path(settings.upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = (upload_dir / filename).resolve()

    # 读取文件并校验大小
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大: {size_mb:.1f}MB, 最大允许: {settings.max_upload_size_mb}MB",
        )

    # 落盘
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(
        f"[上传] 视频已写入磁盘: path={file_path}, size={size_mb:.2f}MB, "
        f"device_code={device_code}, original_name={file.filename}"
    )

    # 创建考试记录
    exam = await exam_service.create_exam(db, device_code, str(file_path))
    await db.flush()

    # 若有 metrics 一并落库 (派生指标在 service 内计算)
    metrics_received = False
    if metrics_payload is not None:
        await exam_service.upsert_cpr_metrics(db, exam.id, device_code, metrics_payload)
        metrics_received = True
        logger.info(f"[上传] 已写入 cpr_metrics: exam_id={exam.id}")

    # 派发 Celery 任务
    task = process_exam_task.delay(exam.id, str(file_path))
    exam.task_id = task.id
    exam.status = "pending"
    await db.flush()

    logger.info(
        f"[上传] 已派发 Celery 任务: exam_id={exam.id}, task_id={task.id}, "
        f"device_code={device_code}, metrics_received={metrics_received}"
    )

    return ExamUploadResponse(
        exam_id=exam.id,
        task_id=task.id,
        device_code=device_code,
        metrics_received=metrics_received,
    )


@router.post("/mock-upload")
async def mock_upload(
    device_code: str = Form(..., min_length=1, max_length=64),
    perfect: bool = Query(default=True, description="是否生成满分指标"),
    db: AsyncSession = Depends(get_async_db),
):
    """调试用 - 不上传视频, 生成假 exam_id + mock 指标, 直接置为 completed 状态。"""
    if perfect:
        metrics_dict = dict(PERFECT_MOCK_METRICS)
    else:
        # 先生成总数, 再从中拆分正确/错误数 - 保证 correct + wrong <= total
        press_total = random.randint(100, 250)
        press_correct = random.randint(int(press_total * 0.7), press_total)
        press_wrong = press_total - press_correct
        blow_total = random.randint(10, 30)
        blow_correct = random.randint(int(blow_total * 0.7), blow_total)
        blow_wrong = blow_total - blow_correct
        metrics_dict = {
            "session_duration_sec": round(random.uniform(120, 240), 1),
            "compression_duration_sec": round(random.uniform(80, 180), 1),
            "press_total": press_total,
            "press_correct": press_correct,
            "press_wrong": press_wrong,
            "press_frequency": round(random.uniform(100, 120), 1),
            "press_avg_depth": round(random.uniform(45, 55), 1),
            "blow_total": blow_total,
            "blow_correct": blow_correct,
            "blow_wrong": blow_wrong,
            "blow_avg_volume": round(random.uniform(400, 600), 1),
            "shoulder_tapped": True,
        }

    metrics_payload = CprMetricsUpload(**metrics_dict)

    exam = await exam_service.create_exam(db, device_code, "<mock>/no-video.mp4")
    exam.status = "completed"
    await db.flush()
    await exam_service.upsert_cpr_metrics(db, exam.id, device_code, metrics_payload)

    derived = derive_scoring_metrics(metrics_payload)
    logger.info(
        f"[mock] 已生成 mock 考试记录: exam_id={exam.id}, device_code={device_code}, "
        f"derived={derived}"
    )

    return {
        "exam_id": exam.id,
        "device_code": device_code,
        "mock": True,
        "perfect": perfect,
        "derived_metrics": derived,
    }


@router.get("/{exam_id}/status", response_model=ExamStatusResponse)
async def get_exam_status(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """查询考试处理进度。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    progress = 0
    stage = None
    substep = None
    detail = None
    if exam.status == "completed":
        progress = 100
    elif exam.status == "processing" and exam.task_id:
        from backend.app.tasks.celery_app import celery_app

        result = celery_app.AsyncResult(exam.task_id)
        if result.state == "PROGRESS" and isinstance(result.info, dict):
            progress = result.info.get("progress", 0)
            stage = result.info.get("stage")
            substep = result.info.get("substep")
            detail = result.info.get("detail")

    return ExamStatusResponse(
        id=exam.id,
        status=exam.status,
        progress=progress,
        stage=stage,
        substep=substep,
        detail=detail,
    )


@router.get("/{exam_id}/result", response_model=ScoreResultResponse)
async def get_exam_result(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取考试评分结果。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    return await exam_service.get_exam_result(db, exam_id)


@router.get("/{exam_id}/timeline", response_model=TimelineResponse)
async def get_exam_timeline(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取考试事件时间轴。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    events = await exam_service.get_exam_timeline(db, exam_id)
    return TimelineResponse(events=events)


@router.get("/{exam_id}/metrics", response_model=CprMetricsResponse)
async def get_exam_metrics(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取该考试关联的 CPR 模拟人指标 (含派生评分指标)。"""
    row = await exam_service.get_cpr_metrics(db, exam_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="该考试无 CPR 指标"
        )
    return row


@router.get("/{exam_id}/video")
async def get_exam_processed_video(
    exam_id: int, db: AsyncSession = Depends(get_async_db)
):
    """下载 AI 标注后的视频文件。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成处理"
        )
    if not exam.processed_video_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="标注视频尚未生成, 请检查 AI 流水线日志",
        )

    # 数据库里既可能是绝对路径, 也可能是历史相对路径
    raw_path = Path(exam.processed_video_url)
    if raw_path.is_absolute():
        video_path = raw_path
    else:
        video_path = (Path(settings.output_dir) / raw_path).resolve()

    if not video_path.exists():
        logger.warning(
            f"[下载] 标注视频文件不存在: db={exam.processed_video_url}, "
            f"resolved={video_path}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注视频文件未找到: {video_path.name}",
        )

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"exam_{exam_id}_annotated.mp4",
    )


def _parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """解析单段 HTTP Range 请求头, 返回 (start, end). 不合法返回 None.

    支持的形式:
        Range: bytes=START-END     -> (START, END)
        Range: bytes=START-        -> (START, file_size - 1)
        Range: bytes=-SUFFIX       -> (file_size - SUFFIX, file_size - 1)
    多段 range (bytes=a-b,c-d) 不支持 - H5 <video> 标签不会发送, 直接判非法
    """
    if not range_header or not range_header.lower().startswith("bytes="):
        return None
    spec = range_header[len("bytes="):].strip()
    if "," in spec:
        return None  # 不支持 multipart range
    if "-" not in spec:
        return None
    start_str, end_str = spec.split("-", 1)
    start_str = start_str.strip()
    end_str = end_str.strip()

    try:
        if start_str == "":
            # 后缀 range: 取末尾 N 字节
            if end_str == "":
                return None
            suffix = int(end_str)
            if suffix <= 0:
                return None
            start = max(file_size - suffix, 0)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
    except ValueError:
        return None

    if start < 0 or end < start or start >= file_size:
        return None
    end = min(end, file_size - 1)
    return start, end


def _iter_video_chunks(file_path: Path, start: int, end: int):
    """流式按块读取文件区间 [start, end] (闭区间), 用于 StreamingResponse 出参"""
    remaining = end - start + 1
    with open(file_path, "rb") as f:
        f.seek(start)
        while remaining > 0:
            read_size = min(_VIDEO_STREAM_CHUNK, remaining)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


@router.get("/{exam_id}/video/play")
async def play_exam_video(
    exam_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """按 exam.video_url 提供原始上传视频的 HTTP Range 流式播放接口.

    专为常规 H5 <video> 标签设计: 支持拖动进度条(Range)、不缓存(考试视频).
    与 /exam/{exam_id}/video 区分: 后者返回 AI 标注后的视频, 此接口返回原始视频.
    """
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if not exam.video_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="该考试无原始视频路径"
        )

    # 数据库里既可能是绝对路径, 也可能是历史相对路径 (相对 upload_dir)
    raw_path = Path(exam.video_url)
    if raw_path.is_absolute():
        video_path = raw_path
    else:
        video_path = (Path(settings.upload_dir) / raw_path).resolve()

    if not video_path.exists() or not video_path.is_file():
        logger.warning(
            f"[播放] 原始视频文件不存在: db={exam.video_url}, resolved={video_path}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"原始视频文件未找到: {video_path.name}",
        )

    file_size = video_path.stat().st_size
    ext = video_path.suffix.lower()
    content_type = VIDEO_CONTENT_TYPE_MAP.get(ext, "application/octet-stream")

    # 通用响应头: H5 浏览器需要 Accept-Ranges 才会启用 Range 请求, 否则只能从头播
    common_headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": "inline",
        "Cache-Control": "no-cache",
    }

    range_header = request.headers.get("range") or request.headers.get("Range")
    if not range_header:
        # 无 Range: 整体返回 200, 仍然带 Accept-Ranges 让浏览器后续可发 Range
        logger.debug(
            f"[播放] 整段返回: exam_id={exam_id}, path={video_path}, size={file_size}"
        )
        common_headers["Content-Length"] = str(file_size)
        return StreamingResponse(
            _iter_video_chunks(video_path, 0, file_size - 1),
            media_type=content_type,
            headers=common_headers,
        )

    parsed = _parse_range_header(range_header, file_size)
    if parsed is None:
        # 非法 Range -> 416, 按 RFC 7233 给出 Content-Range: bytes */<size>
        logger.warning(
            f"[播放] 非法 Range 头: exam_id={exam_id}, range={range_header!r}, "
            f"size={file_size}"
        )
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={
                "Content-Range": f"bytes */{file_size}",
                "Accept-Ranges": "bytes",
            },
        )

    start, end = parsed
    chunk_size = end - start + 1
    common_headers["Content-Length"] = str(chunk_size)
    common_headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    logger.debug(
        f"[播放] Range 分段返回: exam_id={exam_id}, range=bytes {start}-{end}/{file_size}"
    )
    return StreamingResponse(
        _iter_video_chunks(video_path, start, end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=content_type,
        headers=common_headers,
    )


@router.get("/{exam_id}/debug")
async def get_exam_debug_data(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """调试数据接口: 返回转写文本、话术匹配、说话人角色"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    events = await exam_service.get_exam_timeline(db, exam_id)

    audio_events = [e for e in events if e.source == "audio"]
    transcription = []
    voice_matches = []
    speaker_roles = {}

    for e in audio_events:
        data = e.event_data or {}
        if e.event_type == "audio_transcript_segment":
            speaker = data.get("speaker")
            speaker_role = data.get("speaker_role") or "unknown"
            transcription.append(
                {
                    "start": data.get("start", e.time_seconds),
                    "end": data.get("end", e.time_seconds),
                    "text": data.get("text", ""),
                    "speaker": speaker,
                    "speaker_role": speaker_role,
                }
            )
            if speaker:
                speaker_roles[speaker] = speaker_role

        if data.get("matched_text"):
            voice_matches.append(
                {
                    "time": e.time_seconds,
                    "rule_code": e.event_type,
                    "rule_name": data.get("rule_name", ""),
                    "phase": data.get("phase", ""),
                    "score": data.get("score", 0),
                    "similarity": data.get("similarity", 0),
                    "matched_text": data.get("matched_text", ""),
                    "matched_template": data.get("matched_template", ""),
                    "speaker": e.actor,
                    "speaker_role": data.get("speaker_role"),
                    "role_correct": data.get("role_correct", True),
                }
            )

    return {
        "transcription": transcription,
        "voice_matches": voice_matches,
        "speaker_roles": speaker_roles,
    }


@router.get("/{exam_id}/report")
async def get_exam_report(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取 HTML 格式的考试评分报告。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    from fastapi.responses import HTMLResponse

    from backend.app.services.report_service import generate_html_report

    score_data = await exam_service.get_exam_result(db, exam_id)
    html = generate_html_report(
        exam_id=exam_id,
        score_result=score_data,
        created_at=str(exam.created_at),
    )

    return HTMLResponse(content=html)


async def _load_exam_pdf_bytes(exam, exam_id: int, db: AsyncSession) -> bytes:
    """获取考试 PDF 字节流 - 优先读 worker 已落盘的 PDF, 不存在则现场渲染。

    - exam.report_pdf_url 由 Celery worker 写入 (绝对路径)
    - 历史数据可能为空或文件已被清理, 此时回退到 generate_pdf_report 实时生成
    """
    pdf_url = (exam.report_pdf_url or "").strip()
    if pdf_url:
        pdf_path = Path(pdf_url)
        if pdf_path.is_file():
            try:
                return pdf_path.read_bytes()
            except OSError as exc:
                logger.warning(
                    f"[报告] 读取已落盘 PDF 失败, 回退实时生成: "
                    f"exam_id={exam_id}, path={pdf_path}, err={exc}"
                )
        else:
            logger.warning(
                f"[报告] PDF 文件不存在, 回退实时生成: "
                f"exam_id={exam_id}, path={pdf_path}"
            )

    # 回退路径: 现场渲染
    from backend.app.services.report_service import generate_pdf_report

    score_data = await exam_service.get_exam_result(db, exam_id)
    try:
        return generate_pdf_report(
            exam_id=exam_id,
            score_result=score_data,
            created_at=str(exam.created_at),
        )
    except RuntimeError as exc:
        logger.error(f"[报告] PDF 生成失败: exam_id={exam_id}, err={exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF 生成失败: {exc}",
        ) from exc


@router.get("/{exam_id}/report/pdf")
async def get_exam_report_pdf(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """下载 PDF 格式的考核评分报告 - 结构对齐院外心脏骤停急救考核评分表。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    from urllib.parse import quote

    pdf_bytes = await _load_exam_pdf_bytes(exam, exam_id, db)

    filename = f"院外心脏骤停急救考核评分表_{exam_id}.pdf"
    # RFC 5987 - 同时给出 ASCII fallback 与 UTF-8 文件名，确保各浏览器中文不乱码
    ascii_fallback = f"exam_{exam_id}_report.pdf"
    content_disposition = (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/{exam_id}/report/pdf/view")
async def view_exam_report_pdf(
    exam_id: int, db: AsyncSession = Depends(get_async_db)
):
    """浏览器内联查看 PDF 报告 - 与 /report/pdf 共享渲染逻辑, 仅 disposition 不同。

    用途: 远端考核中心 / H5 / 后台管理在 <iframe> 或新标签内直接预览,
    不触发下载. 浏览器依据 Content-Type 与 Content-Disposition=inline 渲染.
    """
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    from urllib.parse import quote

    pdf_bytes = await _load_exam_pdf_bytes(exam, exam_id, db)

    filename = f"院外心脏骤停急救考核评分表_{exam_id}.pdf"
    ascii_fallback = f"exam_{exam_id}_report.pdf"
    # inline + 文件名 - 浏览器内嵌渲染, 用户点击下载时仍能拿到正确文件名
    content_disposition = (
        f'inline; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition,
            # 报告内容随评分而变, 避免浏览器/CDN 缓存到旧版本
            "Cache-Control": "no-cache",
        },
    )


@router.get("s", response_model=ExamListResponse)
async def list_exams(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    """分页获取考试记录列表 - 历史考核记录页面默认返回所有设备的数据."""
    skip = (page - 1) * page_size
    # 内部 service 仍保留按设备过滤能力, 这里固定传 None 表示不过滤
    items, total = await exam_service.list_exams_by_device(
        db, None, skip, page_size
    )
    return ExamListResponse(items=items, total=total)
