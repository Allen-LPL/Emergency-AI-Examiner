from pydantic import BaseModel, Field


class CprMetricsUpload(BaseModel):
    """CPR 模拟人上报指标 - 字段映射自 Android CPRData.java"""

    # 会话时长 (用于派生 ccf)
    session_duration_sec: float = Field(ge=0)
    compression_duration_sec: float = Field(ge=0)

    # 按压核心
    press_total: int = Field(ge=0)
    press_correct: int = Field(ge=0)
    press_wrong: int = Field(ge=0)
    press_frequency: float = Field(ge=0)
    press_avg_depth: float = Field(ge=0)

    # 按压错误分布
    press_too_deep: int = Field(default=0, ge=0)
    press_too_shallow: int = Field(default=0, ge=0)
    press_too_fast: int = Field(default=0, ge=0)
    press_too_slow: int = Field(default=0, ge=0)
    press_no_recoil: int = Field(default=0, ge=0)
    press_wrong_position: int = Field(default=0, ge=0)

    # 通气核心
    blow_total: int = Field(ge=0)
    blow_correct: int = Field(ge=0)
    blow_wrong: int = Field(ge=0)
    blow_avg_volume: float | None = Field(default=None, ge=0)

    # 通气错误分布
    blow_too_much: int = Field(default=0, ge=0)
    blow_too_little: int = Field(default=0, ge=0)
    blow_too_many: int = Field(default=0, ge=0)
    blow_too_few: int = Field(default=0, ge=0)
    blow_into_stomach: int = Field(default=0, ge=0)
    blow_airway_blocked: int = Field(default=0, ge=0)

    # 流程
    shoulder_tapped: bool = False


class CprMetricsResponse(CprMetricsUpload):
    """GET /exam/{id}/metrics 响应 - 包含派生评分指标"""

    id: int
    exam_id: int
    device_code: str
    compression_compliance_rate: float
    ventilation_compliance_rate: float
    ccf_percentage: float

    model_config = {"from_attributes": True}


def derive_scoring_metrics(payload: CprMetricsUpload) -> dict[str, float]:
    """根据原始计数派生评分用聚合指标 (分母 0 时一律记 0)"""
    compression_rate = (
        payload.press_correct / payload.press_total * 100
        if payload.press_total > 0
        else 0.0
    )
    ventilation_rate = (
        payload.blow_correct / payload.blow_total * 100
        if payload.blow_total > 0
        else 0.0
    )
    ccf = (
        payload.compression_duration_sec / payload.session_duration_sec * 100
        if payload.session_duration_sec > 0
        else 0.0
    )
    return {
        "compression_compliance_rate": round(compression_rate, 2),
        "ventilation_compliance_rate": round(ventilation_rate, 2),
        "ccf_percentage": round(ccf, 2),
    }
