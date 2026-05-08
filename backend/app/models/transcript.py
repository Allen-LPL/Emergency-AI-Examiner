"""考试音频时间轴持久化模型.

ExamTranscript: 每个 SpeechSegment 一行, 用于前端时间轴回放与人工审核
SpeakerRoleMap: 每场考试每个 speaker 一行, 标记其 role 与 source (auto/manual/voiceprint)
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class ExamTranscript(Base):
    """考试音频转写段记录 (按时间排序)"""

    __tablename__ = "exam_transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    # 时间轴
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    # 说话人 (如 SPEAKER_00 / UNKNOWN_SPEAKER), 由 pyannote 输出或兜底生成
    speaker: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 角色: doctor / nurse / driver / unknown, 由 SpeakerRoleBinder 写入
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 转写文本 (清洗 + 纠错后)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 段类型: counting / medical_command / assistant_response / family_inquiry / unknown
    segment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 置信度 (Paraformer 不直接给, 通常为空)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SpeakerRoleMap(Base):
    """speaker → role 映射记录, 每场考试每个 speaker 一行."""

    __tablename__ = "speaker_role_maps"
    __table_args__ = (
        UniqueConstraint("exam_id", "speaker", name="uq_exam_speaker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    speaker: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    # source 标识来源: auto (内容推断) / manual (人工标注) / voiceprint (声纹注册)
    source: Mapped[str] = mapped_column(String(16), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
