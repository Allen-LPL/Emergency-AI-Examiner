from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.cpr_metrics import CprMetrics
from backend.app.models.event import ExamEvent
from backend.app.models.exam import Exam
from backend.app.models.score import ExamScore
from backend.app.schemas.cpr_metrics import CprMetricsUpload, derive_scoring_metrics
from backend.app.schemas.score import PhaseScore


async def create_exam(db: AsyncSession, device_code: str, video_path: str) -> Exam:
    """创建考试记录 - 以设备码作为归属键, user_id 设备直连场景留空"""
    exam = Exam(
        device_code=device_code,
        user_id=None,
        video_url=video_path,
        status="pending",
    )
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    return exam


async def get_exam(db: AsyncSession, exam_id: int) -> Exam | None:
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    return result.scalar_one_or_none()


async def update_exam_status(
    db: AsyncSession, exam_id: int, status: str, task_id: str | None = None
) -> None:
    exam = await get_exam(db, exam_id)
    if exam:
        exam.status = status
        if task_id:
            exam.task_id = task_id
        await db.flush()


async def upsert_cpr_metrics(
    db: AsyncSession,
    exam_id: int,
    device_code: str,
    payload: CprMetricsUpload,
) -> CprMetrics:
    """插入或更新 CPR 指标行 - 同时落原始计数与派生指标"""
    derived = derive_scoring_metrics(payload)
    existing = await db.execute(
        select(CprMetrics).where(CprMetrics.exam_id == exam_id)
    )
    row = existing.scalar_one_or_none()

    data = payload.model_dump()
    data.update(derived)
    data["device_code"] = device_code

    if row:
        for field, value in data.items():
            setattr(row, field, value)
    else:
        row = CprMetrics(exam_id=exam_id, **data)
        db.add(row)

    await db.flush()
    await db.refresh(row)
    return row


async def get_cpr_metrics(db: AsyncSession, exam_id: int) -> CprMetrics | None:
    result = await db.execute(
        select(CprMetrics).where(CprMetrics.exam_id == exam_id)
    )
    return result.scalar_one_or_none()


async def get_exam_result(db: AsyncSession, exam_id: int) -> dict:
    result = await db.execute(select(ExamScore).where(ExamScore.exam_id == exam_id))
    scores = result.scalars().all()

    exam = await get_exam(db, exam_id)
    total = sum(s.actual_score for s in scores)

    phase_map: dict[str, dict[str, float]] = defaultdict(
        lambda: {"score": 0.0, "max_score": 0.0}
    )
    for s in scores:
        phase_map[s.phase]["score"] += s.actual_score
        phase_map[s.phase]["max_score"] += s.max_score

    return {
        "exam_id": exam_id,
        "total_score": exam.total_score if exam else total,
        "max_total": 100.0,
        "items": scores,
        "phase_scores": {
            k: PhaseScore(score=v["score"], max_score=v["max_score"])
            for k, v in phase_map.items()
        },
    }


async def get_exam_timeline(db: AsyncSession, exam_id: int) -> list[ExamEvent]:
    result = await db.execute(
        select(ExamEvent)
        .where(ExamEvent.exam_id == exam_id)
        .order_by(ExamEvent.time_seconds)
    )
    return list(result.scalars().all())


async def list_exams_by_device(
    db: AsyncSession, device_code: str, skip: int = 0, limit: int = 20
) -> tuple[list[Exam], int]:
    """按设备码分页查询考试记录"""
    count_result = await db.execute(
        select(func.count())
        .select_from(Exam)
        .where(Exam.device_code == device_code)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Exam)
        .where(Exam.device_code == device_code)
        .order_by(Exam.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


def save_exam_events_sync(db_session, exam_id: int, events: list[dict]) -> None:
    for event in events:
        event_type = (
            event.get("event_type")
            or event.get("rule_code")
            or event.get("action")
            or "unknown"
        )
        if isinstance(event_type, str):
            event_type = event_type.strip() or "unknown"
        else:
            event_type = "unknown"

        db_event = ExamEvent(
            exam_id=exam_id,
            time_seconds=event.get("time", 0.0),
            actor=event.get("actor"),
            event_type=event_type,
            event_data=event.get("data"),
            source=event.get("source", "fusion"),
            confidence=event.get("confidence", 1.0),
        )
        db_session.add(db_event)
    db_session.flush()


def save_exam_scores_sync(db_session, exam_id: int, score_result: dict) -> None:
    for item in score_result.get("items", []):
        db_score = ExamScore(
            exam_id=exam_id,
            phase=item.get("phase", ""),
            rule_code=item.get("rule_code", ""),
            rule_name=item.get("rule_name", ""),
            max_score=item.get("max_score", 0.0),
            actual_score=item.get("actual_score", 0.0),
            deduction_reason=item.get("deduction_reason"),
            evidence_data=item.get("evidence"),
        )
        db_session.add(db_score)
    db_session.flush()
