import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
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

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


@router.post("/upload", response_model=ExamUploadResponse)
async def upload_exam(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = upload_dir / filename

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大: {size_mb:.1f}MB，最大允许: {settings.max_upload_size_mb}MB",
        )

    with open(file_path, "wb") as f:
        f.write(content)

    exam = await exam_service.create_exam(db, current_user.id, str(file_path))
    await db.flush()

    task = process_exam_task.delay(exam.id, str(file_path))
    exam.task_id = task.id
    exam.status = "pending"
    await db.flush()

    return ExamUploadResponse(exam_id=exam.id, task_id=task.id)


@router.get("/{exam_id}/status", response_model=ExamStatusResponse)
async def get_exam_status(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
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
    exam = await exam_service.get_exam(db, exam_id)
    if not exam or exam.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    events = await exam_service.get_exam_timeline(db, exam_id)
    return TimelineResponse(events=events)


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

    audio_events = [e for e in events if e.source == "audio"]
    transcription = []
    voice_matches = []
    speaker_roles = {}

    for e in audio_events:
        data = e.event_data or {}
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
    exam = await exam_service.get_exam(db, exam_id)
    if not exam or exam.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    from backend.app.services.report_service import generate_html_report

    score_data = await exam_service.get_exam_result(db, exam_id)
    html = generate_html_report(
        exam_id=exam_id,
        score_result=score_data,
        created_at=str(exam.created_at),
    )
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html)


@router.get("s", response_model=ExamListResponse)
async def list_exams(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    skip = (page - 1) * page_size
    items, total = await exam_service.list_user_exams(
        db, current_user.id, skip, page_size
    )
    return ExamListResponse(items=items, total=total)
