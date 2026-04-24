from pydantic import BaseModel


class EventResponse(BaseModel):
    id: int
    exam_id: int
    time_seconds: float
    actor: str | None
    event_type: str
    event_data: dict | None
    source: str
    confidence: float

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    events: list[EventResponse]
