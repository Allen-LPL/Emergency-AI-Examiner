from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.event import ExamEvent
from backend.app.models.exam import Exam
from backend.app.models.score import ExamScore
from backend.app.schemas.score import PhaseScore


async def create_exam(db: AsyncSession, user_id: int, video_path: str) -> Exam:
    exam = Exam(user_id=user_id, video_url=video_path, status="pending")
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


async def list_user_exams(
    db: AsyncSession, user_id: int, skip: int = 0, limit: int = 20
) -> tuple[list[Exam], int]:
    count_result = await db.execute(
        select(func.count()).select_from(Exam).where(Exam.user_id == user_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Exam)
        .where(Exam.user_id == user_id)
        .order_by(Exam.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


def save_exam_events_sync(db_session, exam_id: int, events: list[dict]) -> None:
    for event in events:
        db_event = ExamEvent(
            exam_id=exam_id,
            time_seconds=event.get("time", 0.0),
            actor=event.get("actor"),
            event_type=event.get("event_type", "unknown"),
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
