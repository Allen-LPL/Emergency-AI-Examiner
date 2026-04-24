from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class ExamScore(Base):
    __tablename__ = "exam_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), index=True)
    phase: Mapped[str] = mapped_column(String(50))
    rule_code: Mapped[str] = mapped_column(String(100))
    rule_name: Mapped[str] = mapped_column(String(200))
    max_score: Mapped[float] = mapped_column(Float)
    actual_score: Mapped[float] = mapped_column(Float, default=0.0)
    deduction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    exam = relationship("Exam", back_populates="scores")
