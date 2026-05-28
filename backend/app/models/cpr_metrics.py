from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class CprMetrics(Base):
    """CPR 模拟人上报指标 - 字段映射自 Android CPRData.java"""

    __tablename__ = "cpr_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exams.id"), unique=True, index=True
    )
    # 冗余存设备码, 便于跨 exam 按设备聚合
    device_code: Mapped[str] = mapped_column(String(64), index=True)

    # 会话时长 (用于派生 ccf_percentage)
    session_duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    compression_duration_sec: Mapped[float] = mapped_column(Float, default=0.0)

    # 按压核心计数
    press_total: Mapped[int] = mapped_column(Integer, default=0)
    press_correct: Mapped[int] = mapped_column(Integer, default=0)
    press_wrong: Mapped[int] = mapped_column(Integer, default=0)
    press_frequency: Mapped[float] = mapped_column(Float, default=0.0)  # 按压频率 (次/分钟)
    press_avg_depth: Mapped[float] = mapped_column(Float, default=0.0)  # 平均按压深度 (mm)

    # 按压错误分布
    press_too_deep: Mapped[int] = mapped_column(Integer, default=0)
    press_too_shallow: Mapped[int] = mapped_column(Integer, default=0)
    press_too_fast: Mapped[int] = mapped_column(Integer, default=0)
    press_too_slow: Mapped[int] = mapped_column(Integer, default=0)
    press_no_recoil: Mapped[int] = mapped_column(Integer, default=0)
    press_wrong_position: Mapped[int] = mapped_column(Integer, default=0)

    # 通气核心计数
    blow_total: Mapped[int] = mapped_column(Integer, default=0)
    blow_correct: Mapped[int] = mapped_column(Integer, default=0)
    blow_wrong: Mapped[int] = mapped_column(Integer, default=0)
    blow_avg_volume: Mapped[float | None] = mapped_column(Float, nullable=True)  # 平均通气量 (ml)

    # 通气错误分布
    blow_too_much: Mapped[int] = mapped_column(Integer, default=0)
    blow_too_little: Mapped[int] = mapped_column(Integer, default=0)
    blow_too_many: Mapped[int] = mapped_column(Integer, default=0)
    blow_too_few: Mapped[int] = mapped_column(Integer, default=0)
    blow_into_stomach: Mapped[int] = mapped_column(Integer, default=0)
    blow_airway_blocked: Mapped[int] = mapped_column(Integer, default=0)

    # 流程
    shoulder_tapped: Mapped[bool] = mapped_column(Boolean, default=False)

    # 服务器派生的评分指标 (入库便于评分规则直接消费 + GET 接口回显)
    compression_compliance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    ventilation_compliance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    ccf_percentage: Mapped[float] = mapped_column(Float, default=0.0)
