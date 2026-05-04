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
    """Celery 异步任务: 执行 AI 分析管线并将结果存入数据库。"""
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

        # 查询关联的传感器数据（CPR 模拟人数据）
        from backend.app.models.sensor import SensorData

        sensor_row = db.query(SensorData).filter(SensorData.exam_id == exam_id).first()
        sensor_dict = None
        if sensor_row:
            sensor_dict = {
                "compression_compliance_rate": sensor_row.compression_compliance_rate,
                "ventilation_compliance_rate": sensor_row.ventilation_compliance_rate,
                "ccf_percentage": sensor_row.ccf_percentage,
            }

        # 执行 AI 分析管线（视频分析 + 音频分析 + 融合评分 + 标注视频生成）
        pipeline = ExaminationPipeline(
            config=get_ai_config(), progress_callback=_progress
        )
        result = pipeline.process(video_path, sensor_data=sensor_dict)

        self.update_state(state="PROGRESS", meta={"progress": 80})

        # 保存事件到数据库
        events = result.get("events", [])
        save_exam_events_sync(db, exam_id, events)

        self.update_state(state="PROGRESS", meta={"progress": 90})

        # 保存评分结果到数据库
        score_result = result.get("scores", {})
        save_exam_scores_sync(db, exam_id, score_result)

        # 保存标注视频路径到数据库
        processed_video_path = result.get("processed_video_path", "")
        if processed_video_path:
            exam.processed_video_url = processed_video_path

        exam.total_score = score_result.get("total_score", 0.0)
        exam.status = "completed"
        db.commit()

        logger.info(f"Exam {exam_id} completed with score {exam.total_score}")
        return {
            "status": "completed",
            "exam_id": exam_id,
            "total_score": exam.total_score,
            "processed_video_path": processed_video_path,
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
