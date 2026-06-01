from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Exam(Base):
    """考试记录模型 - 以设备码标识数据来源, 不再绑定登录用户"""

    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 设备码 - 数据来源标识, 替代原有 user_id 用作归属过滤键
    device_code: Mapped[str] = mapped_column(String(64), index=True)
    # 兼容老多用户模式保留, 设备直连场景一律为 NULL
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    # 原始上传视频路径
    video_url: Mapped[str] = mapped_column(String(500))
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # AI 标注后的视频路径(含姿态骨架、关键点、动作标签、语音字幕)
    processed_video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # AI 生成的 PDF 评分报告路径(绝对路径), 由 Celery 任务在评分完成后落盘
    report_pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    events = relationship(
        "ExamEvent", back_populates="exam", cascade="all, delete-orphan"
    )
    scores = relationship(
        "ExamScore", back_populates="exam", cascade="all, delete-orphan"
    )
