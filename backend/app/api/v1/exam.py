import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user
from backend.app.config import settings
from backend.app.database import get_async_db
from backend.app.models.user import User
from backend.app.schemas.event import TimelineResponse
from backend.app.schemas.exam import (
    ExamListResponse,
    ExamResponse,
    ExamStatusResponse,
    ExamUploadResponse,
)
from backend.app.schemas.score import ScoreResultResponse
from backend.app.services import exam_service
from backend.app.tasks.exam_task import process_exam_task

router = APIRouter(prefix="/exam", tags=["考试"])

# 允许上传的视频文件扩展名
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


@router.post("/upload", response_model=ExamUploadResponse)
async def upload_exam(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """上传考试视频，校验格式和大小后写入磁盘，创建考试记录并触发异步 AI 分析任务。"""
    # 校验文件扩展名
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 确保上传目录存在, 并解析为绝对路径
    # 之所以使用绝对路径: api 容器与 celery_worker 容器是两个独立进程,
    # 它们共享 ./uploads 绑定挂载, 但工作目录可能不同, 相对路径会出现解析歧义.
    upload_dir = Path(settings.upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名, 避免冲突
    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = (upload_dir / filename).resolve()

    # 读取文件内容并校验大小
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大: {size_mb:.1f}MB，最大允许: {settings.max_upload_size_mb}MB",
        )

    # 将视频文件写入磁盘 (此处必须真正落盘, 失败会抛 IOError 由 FastAPI 转 500)
    with open(file_path, "wb") as f:
        f.write(content)

    # 写盘成功后立即记录绝对路径与文件大小, 便于排查"宿主机看不到 uploads 文件"类问题
    logger.info(
        f"[上传] 视频已写入磁盘: path={file_path}, size={size_mb:.2f}MB, "
        f"original_name={file.filename}"
    )

    # 创建考试记录并触发 Celery 异步处理任务. video_url 入库使用绝对路径字符串.
    exam = await exam_service.create_exam(db, current_user.id, str(file_path))
    await db.flush()

    task = process_exam_task.delay(exam.id, str(file_path))
    exam.task_id = task.id
    exam.status = "pending"
    await db.flush()

    logger.info(
        f"[上传] 已派发 Celery 任务: exam_id={exam.id}, task_id={task.id}, "
        f"video_path={file_path}"
    )

    return ExamUploadResponse(exam_id=exam.id, task_id=task.id)


@router.get("/{exam_id}/status", response_model=ExamStatusResponse)
async def get_exam_status(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """查询考试处理进度，包含当前阶段、子步骤和详细信息。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam or exam.user_id != current_user.id:
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
        # 从 Celery 任务状态中读取实时进度
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
async def get_exam_result(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取考试评分结果，包含各阶段得分明细。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam or exam.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    return await exam_service.get_exam_result(db, exam_id)


@router.get("/{exam_id}/timeline", response_model=TimelineResponse)
async def get_exam_timeline(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取考试事件时间轴，按时间排序返回所有视频/音频/融合事件。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam or exam.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    events = await exam_service.get_exam_timeline(db, exam_id)
    return TimelineResponse(events=events)


@router.get("/{exam_id}/video")
async def get_exam_processed_video(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """下载 AI 标注后的视频文件（含姿态骨架、关键点、动作标签、语音字幕）。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam or exam.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成处理"
        )
    if not exam.processed_video_url:
        # 流水线尚未生成或生成失败 (可在 celery_worker 日志中搜索 "标注视频" 关键字定位)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="标注视频尚未生成, 请检查 AI 流水线日志",
        )

    # 数据库中存的可能是绝对路径, 也可能是历史的相对路径; 这里做兼容解析
    raw_path = Path(exam.processed_video_url)
    if raw_path.is_absolute():
        video_path = raw_path
    else:
        # 相对路径按 settings.output_dir 为基准解析, 兼容 "outputs/xxx.mp4" 这类老数据
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


@router.get("/{exam_id}/debug")
async def get_exam_debug_data(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """调试数据接口(无鉴权): 返回转写文本、话术匹配、说话人角色"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    events = await exam_service.get_exam_timeline(db, exam_id)

    # 筛选音频类事件
    audio_events = [e for e in events if e.source == "audio"]
    transcription = []
    voice_matches = []
    speaker_roles = {}

    for e in audio_events:
        data = e.event_data or {}
        # 提取转写片段
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

        # 提取话术匹配结果
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
async def get_exam_report(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取 HTML 格式的考试评分报告。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam or exam.user_id != current_user.id:
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


@router.get("s", response_model=ExamListResponse)
async def list_exams(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """分页获取当前用户的考试记录列表。"""
    skip = (page - 1) * page_size
    items, total = await exam_service.list_user_exams(
        db, current_user.id, skip, page_size
    )
    return ExamListResponse(items=items, total=total)
