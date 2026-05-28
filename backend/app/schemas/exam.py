from datetime import datetime

from pydantic import BaseModel


class ExamResponse(BaseModel):
    id: int
    device_code: str
    video_url: str
    processed_video_url: str | None = None
    status: str
    total_score: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExamStatusResponse(BaseModel):
    id: int
    status: str
    progress: int = 0
    stage: str | None = None
    substep: str | None = None
    detail: str | None = None


class ExamUploadResponse(BaseModel):
    exam_id: int
    task_id: str
    device_code: str
    metrics_received: bool
    status: str = "pending"


class ExamListResponse(BaseModel):
    items: list[ExamResponse]
    total: int
