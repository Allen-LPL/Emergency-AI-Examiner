from loguru import logger

from backend.app.database import get_sync_db
from backend.app.models.exam import Exam
from backend.app.services.exam_service import (
    save_exam_events_sync,
    save_exam_scores_sync,
)
from backend.app.tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def process_exam_task(self, exam_id: int, video_path: str):
    logger.info(f"Processing exam {exam_id}, video: {video_path}")
    db_gen = get_sync_db()
    db = next(db_gen)

    try:
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            logger.error(f"Exam {exam_id} not found")
            return {"status": "failed", "error": "Exam not found"}

        exam.status = "processing"
        db.flush()

        self.update_state(state="PROGRESS", meta={"progress": 10})

        from ai_engine.config import get_ai_config
        from ai_engine.pipeline import ExaminationPipeline

        def _progress(progress, stage, substep, detail=""):
            self.update_state(
                state="PROGRESS",
                meta={
                    "progress": progress,
                    "stage": stage,
                    "substep": substep,
                    "detail": detail,
                },
            )

        pipeline = ExaminationPipeline(
            config=get_ai_config(), progress_callback=_progress
        )
        result = pipeline.process(video_path)

        self.update_state(state="PROGRESS", meta={"progress": 80})

        events = result.get("events", [])
        save_exam_events_sync(db, exam_id, events)

        self.update_state(state="PROGRESS", meta={"progress": 90})

        score_result = result.get("scores", {})
        save_exam_scores_sync(db, exam_id, score_result)

        exam.total_score = score_result.get("total_score", 0.0)
        exam.status = "completed"
        db.commit()

        logger.info(f"Exam {exam_id} completed with score {exam.total_score}")
        return {
            "status": "completed",
            "exam_id": exam_id,
            "total_score": exam.total_score,
        }

    except Exception as exc:
        db.rollback()
        logger.error(f"Exam {exam_id} processing failed: {exc}")

        try:
            exam = db.query(Exam).filter(Exam.id == exam_id).first()
            if exam:
                exam.status = "failed"
                exam.error_message = str(exc)[:500]
                db.commit()
        except Exception:
            db.rollback()

        raise self.retry(exc=exc)

    finally:
        try:
            next(db_gen, None)
        except StopIteration:
            pass
