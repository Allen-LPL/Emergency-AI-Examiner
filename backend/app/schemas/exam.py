from datetime import datetime

from pydantic import BaseModel


class ExamResponse(BaseModel):
    id: int
    user_id: int
    video_url: str
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
    status: str = "pending"


class ExamListResponse(BaseModel):
    items: list[ExamResponse]
    total: int
