from pathlib import Path

from loguru import logger

from backend.app.database import get_sync_db
from backend.app.models.exam import Exam
from backend.app.services.exam_service import (
    save_exam_events_sync,
    save_exam_scores_sync,
)
from backend.app.services.transcript_service import (
    dump_audio_timeline_json,
    save_audio_timeline_sync,
)
from backend.app.tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def process_exam_task(self, exam_id: int, video_path: str):
    """Celery 异步任务: 执行 AI 分析管线并将结果存入数据库。

    主要步骤:
        1. 标记考试状态为 processing
        2. 调用 ExaminationPipeline 完成视频/音频/融合/评分/标注视频生成
        3. 把事件、评分明细、标注视频路径写回数据库
        4. 任意阶段异常都会回滚事务、记录中文堆栈, 并交给 Celery 重试
    """
    logger.info(f"[考试 {exam_id}] 开始处理视频: {video_path}")

    # 入参校验: video_path 必须真实存在, 否则直接判失败 (防止 retry 浪费 GPU 时间)
    if not Path(video_path).exists():
        logger.error(
            f"[考试 {exam_id}] 视频文件不存在, 终止任务: video_path={video_path}"
        )
        db_gen = get_sync_db()
        db = next(db_gen)
        try:
            exam = db.query(Exam).filter(Exam.id == exam_id).first()
            if exam:
                exam.status = "failed"
                exam.error_message = f"视频文件不存在: {video_path}"
                db.commit()
        finally:
            try:
                next(db_gen, None)
            except StopIteration:
                pass
        return {"status": "failed", "error": "video file not found"}

    db_gen = get_sync_db()
    db = next(db_gen)

    try:
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            logger.error(f"[考试 {exam_id}] 数据库未找到考试记录, 任务终止")
            return {"status": "failed", "error": "Exam not found"}

        exam.status = "processing"
        db.flush()

        self.update_state(state="PROGRESS", meta={"progress": 10})

        from ai_engine.config import get_ai_config
        from ai_engine.pipeline import ExaminationPipeline

        def _progress(progress, stage, substep, detail=""):
            # Celery 进度回调: 把流水线 0~100 的进度透传给前端轮询接口
            self.update_state(
                state="PROGRESS",
                meta={
                    "progress": progress,
                    "stage": stage,
                    "substep": substep,
                    "detail": detail,
                },
            )

        # 查询关联的传感器数据 (CPR 模拟人数据, 可选)
        from backend.app.models.sensor import SensorData

        sensor_row = db.query(SensorData).filter(SensorData.exam_id == exam_id).first()
        sensor_dict = None
        if sensor_row:
            sensor_dict = {
                "compression_compliance_rate": sensor_row.compression_compliance_rate,
                "ventilation_compliance_rate": sensor_row.ventilation_compliance_rate,
                "ccf_percentage": sensor_row.ccf_percentage,
            }
            logger.info(f"[考试 {exam_id}] 已加载传感器数据: {sensor_dict}")

        # 执行 AI 分析管线 (视频分析 + 音频分析 + 融合评分 + 标注视频生成)
        logger.info(f"[考试 {exam_id}] 启动 AI 流水线")
        pipeline = ExaminationPipeline(
            config=get_ai_config(), progress_callback=_progress
        )
        result = pipeline.process(video_path, sensor_data=sensor_dict)
        logger.info(
            f"[考试 {exam_id}] AI 流水线返回: events={len(result.get('events', []))}, "
            f"timeline={len(result.get('timeline', []))}, "
            f"processed_video_path={result.get('processed_video_path', '')!r}"
        )

        self.update_state(state="PROGRESS", meta={"progress": 80})

        # 保存事件到数据库
        events = result.get("events", [])
        save_exam_events_sync(db, exam_id, events)
        logger.info(f"[考试 {exam_id}] 已写入事件 {len(events)} 条")

        self.update_state(state="PROGRESS", meta={"progress": 87})

        # 保存音频时间轴 (transcripts + speaker_role_maps + outputs JSON)
        audio_result = result.get("audio_result") or {}
        if audio_result:
            try:
                save_audio_timeline_sync(db, exam_id, audio_result)
                # 同步落 JSON, 路径用 settings.output_dir 保证 api 容器也能读
                from backend.app.config import settings as _settings

                dump_audio_timeline_json(
                    output_dir=_settings.output_dir,
                    exam_id=exam_id,
                    audio_result=audio_result,
                )
            except Exception as exc:
                logger.exception(
                    f"[考试 {exam_id}] 音频时间轴持久化失败: {exc} (流程继续)"
                )

        self.update_state(state="PROGRESS", meta={"progress": 90})

        # 保存评分结果到数据库
        score_result = result.get("scores", {})
        save_exam_scores_sync(db, exam_id, score_result)
        logger.info(
            f"[考试 {exam_id}] 已写入评分明细 {len(score_result.get('items', []))} 项, "
            f"total_score={score_result.get('total_score', 0.0)}"
        )

        # 保存标注视频路径到数据库 (统一入库为绝对路径, 跨容器/跨工作目录可寻址)
        processed_video_path = result.get("processed_video_path", "")
        if processed_video_path:
            abs_processed = str(Path(processed_video_path).resolve())
            exam.processed_video_url = abs_processed
            logger.info(
                f"[考试 {exam_id}] 标注视频路径已写入数据库: {abs_processed}"
            )
        else:
            logger.warning(
                f"[考试 {exam_id}] 流水线未返回标注视频路径 (可能因姿态检测无结果或视频写出失败), "
                f"processed_video_url 字段保持为 NULL"
            )

        exam.total_score = score_result.get("total_score", 0.0)
        exam.status = "completed"
        db.commit()

        logger.info(
            f"[考试 {exam_id}] 处理完成, total_score={exam.total_score}, "
            f"processed_video_url={exam.processed_video_url}"
        )
        return {
            "status": "completed",
            "exam_id": exam_id,
            "total_score": exam.total_score,
            "processed_video_path": processed_video_path,
        }

    except Exception as exc:
        # 主流程异常: 回滚事务, 用 logger.exception 输出完整堆栈
        db.rollback()
        logger.exception(f"[考试 {exam_id}] 处理失败: {exc}")

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
