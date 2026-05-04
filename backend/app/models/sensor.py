from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class SensorData(Base):
    __tablename__ = "sensor_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exams.id"), unique=True, index=True
    )
    compression_compliance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    ventilation_compliance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    ccf_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    avg_compression_depth: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_compression_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_compressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ventilations: Mapped[int | None] = mapped_column(Integer, nullable=True)
