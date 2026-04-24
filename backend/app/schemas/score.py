from pydantic import BaseModel


class ScoreItemResponse(BaseModel):
    phase: str
    rule_code: str
    rule_name: str
    max_score: float
    actual_score: float
    deduction_reason: str | None

    model_config = {"from_attributes": True}


class PhaseScore(BaseModel):
    score: float
    max_score: float


class ScoreResultResponse(BaseModel):
    exam_id: int
    total_score: float
    max_total: float = 100.0
    items: list[ScoreItemResponse]
    phase_scores: dict[str, PhaseScore]
