from pydantic import BaseModel, Field


class SensorDataUpload(BaseModel):
    exam_id: int
    compression_compliance_rate: float = Field(ge=0, le=100)
    ventilation_compliance_rate: float = Field(ge=0, le=100)
    ccf_percentage: float = Field(ge=0, le=100)
    avg_compression_depth: float | None = Field(default=None)
    avg_compression_rate: float | None = Field(default=None)
    total_compressions: int | None = Field(default=None)
    total_ventilations: int | None = Field(default=None)


class SensorDataResponse(BaseModel):
    id: int
    exam_id: int
    compression_compliance_rate: float
    ventilation_compliance_rate: float
    ccf_percentage: float
    avg_compression_depth: float | None
    avg_compression_rate: float | None
    total_compressions: int | None
    total_ventilations: int | None

    model_config = {"from_attributes": True}
