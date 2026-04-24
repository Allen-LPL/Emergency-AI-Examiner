from celery import Celery

from backend.app.config import settings

celery_app = Celery(
    "emergency_examiner",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)

celery_app.autodiscover_tasks(["backend.app.tasks"])
