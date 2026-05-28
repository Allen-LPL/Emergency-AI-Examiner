# 设备直连改造 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除登录鉴权;合并视频上传与传感器数据上报为单个 multipart 接口;基于 `CPRData.java` 重新设计 CPR 指标数据模型,服务器侧派生评分指标。

**Architecture:** 删除 `user.py` 与 `sensor.py` 两个路由模块,以 `device_code` 替代 `current_user` 作为数据归属键;新增 `cpr_metrics` 表存设备原始计数器与服务器派生指标;合并上传接口接收 `file + device_code + metrics(JSON)`。

**Tech Stack:** FastAPI · SQLAlchemy 2.0 异步 · PostgreSQL · Celery · multipart/form-data

**Spec:** `docs/superpowers/specs/2026-05-28-device-api-refactor-design.md`

**说明:** backend 当前无单元测试基础(`tests/` 只覆盖 `ai_engine/`),本计划不强制 TDD;每个 Task 末尾以"导入烟测 / uvicorn 启动 / curl 调用"作为验证手段。

---

## 文件结构

**新建**
- `backend/app/models/cpr_metrics.py` — CPR 指标 ORM 模型(原始计数 + 派生指标)
- `backend/app/schemas/cpr_metrics.py` — 上报输入 schema 与派生指标计算 helper
- `scripts/reset_db.sh` — 远端执行 DROP TABLE 重建库的运维脚本
- `docs/device_api.md` — 中文设备工程师对接文档

**修改**
- `backend/app/models/exam.py` — 加 `device_code`,`user_id` 改 nullable
- `backend/app/models/__init__.py` — 替换 `SensorData` 导出为 `CprMetrics`
- `backend/app/schemas/exam.py` — `ExamResponse` 加 `device_code` 删 `user_id`;`ExamUploadResponse` 加 `device_code` 与 `metrics_received`
- `backend/app/api/deps.py` — 删除 `get_current_user` 与 `oauth2_scheme`
- `backend/app/api/v1/router.py` — 不再 include user/sensor 路由
- `backend/app/api/v1/exam.py` — 合并上传接口、所有 GET 去鉴权、新增 metrics GET 与 mock-upload
- `backend/app/services/exam_service.py` — `create_exam` 加 `device_code`;`list_user_exams` → `list_exams_by_device`;新增 `upsert_cpr_metrics / get_cpr_metrics`
- `backend/app/tasks/exam_task.py` — 从 `cpr_metrics` 表读取派生指标
- `backend/app/main.py` — 清理未使用的 `User` 导入

**删除**
- `backend/app/api/v1/user.py`
- `backend/app/api/v1/sensor.py`
- `backend/app/core/security.py`
- `backend/app/schemas/user.py`
- `backend/app/schemas/sensor.py`
- `backend/app/models/sensor.py`

---

### Task 1: 清理鉴权与旧路由

**Files:**
- Delete: `backend/app/api/v1/user.py`
- Delete: `backend/app/api/v1/sensor.py`
- Delete: `backend/app/core/security.py`
- Delete: `backend/app/schemas/user.py`
- Delete: `backend/app/schemas/sensor.py`
- Delete: `backend/app/models/sensor.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: 删除六个文件**

```bash
rm backend/app/api/v1/user.py
rm backend/app/api/v1/sensor.py
rm backend/app/core/security.py
rm backend/app/schemas/user.py
rm backend/app/schemas/sensor.py
rm backend/app/models/sensor.py
```

- [ ] **Step 2: 重写 `backend/app/api/deps.py` 为空文件占位**

文件保留但只放注释,留作后续放置非鉴权依赖。

```python
# backend/app/api/deps.py
# 通用依赖占位文件; 鉴权依赖已移除, 设备直连接口不再需要 current_user
```

- [ ] **Step 3: 重写 `backend/app/api/v1/router.py`**

```python
# backend/app/api/v1/router.py
from fastapi import APIRouter

from backend.app.api.v1.exam import router as exam_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(exam_router)
```

- [ ] **Step 4: 烟测 — 导入应仍能通过(此时 exam.py 还在引用 User/get_current_user,会报错;先暂存,Task 5 修复)**

由于 `exam.py` 还在导入 `User` 与 `get_current_user`,目前会失败。Task 5 完成前 backend 暂不可启动。继续推进。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 删除鉴权模块与 sensor 旧路由"
```

---

### Task 2: 数据模型重构

**Files:**
- Modify: `backend/app/models/exam.py`
- Create: `backend/app/models/cpr_metrics.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 修改 `backend/app/models/exam.py`**

将完整内容替换为:

```python
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
```

- [ ] **Step 2: 创建 `backend/app/models/cpr_metrics.py`**

```python
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
    press_frequency: Mapped[float] = mapped_column(Float, default=0.0)
    press_avg_depth: Mapped[float] = mapped_column(Float, default=0.0)

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
    blow_avg_volume: Mapped[float | None] = mapped_column(Float, nullable=True)

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
```

- [ ] **Step 3: 替换 `backend/app/models/__init__.py`**

```python
from backend.app.models.cpr_metrics import CprMetrics
from backend.app.models.event import ExamEvent
from backend.app.models.exam import Exam
from backend.app.models.score import ExamScore
from backend.app.models.transcript import ExamTranscript, SpeakerRoleMap
from backend.app.models.user import User

__all__ = [
    "User",
    "Exam",
    "ExamEvent",
    "ExamScore",
    "CprMetrics",
    "ExamTranscript",
    "SpeakerRoleMap",
]
```

- [ ] **Step 4: 模型导入烟测**

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
python -c "from backend.app.models import CprMetrics, Exam; print('models ok', CprMetrics.__tablename__, Exam.__tablename__)"
```

Expected: `models ok cpr_metrics exams`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 重构数据模型 - Exam 加 device_code, 新增 cpr_metrics 表"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/cpr_metrics.py`
- Modify: `backend/app/schemas/exam.py`

- [ ] **Step 1: 创建 `backend/app/schemas/cpr_metrics.py`**

```python
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
```

- [ ] **Step 2: 重写 `backend/app/schemas/exam.py`**

```python
from datetime import datetime

from pydantic import BaseModel


class ExamResponse(BaseModel):
    id: int
    device_code: str
    video_url: str
    processed_video_url: str | None = None
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
    device_code: str
    metrics_received: bool
    status: str = "pending"


class ExamListResponse(BaseModel):
    items: list[ExamResponse]
    total: int
```

- [ ] **Step 3: Schema 烟测**

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
python -c "
from backend.app.schemas.cpr_metrics import CprMetricsUpload, derive_scoring_metrics
m = CprMetricsUpload(
    session_duration_sec=180, compression_duration_sec=145,
    press_total=200, press_correct=185, press_wrong=15,
    press_frequency=112, press_avg_depth=53,
    blow_total=20, blow_correct=18, blow_wrong=2,
)
print(derive_scoring_metrics(m))
"
```

Expected: `{'compression_compliance_rate': 92.5, 'ventilation_compliance_rate': 90.0, 'ccf_percentage': 80.56}`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: 新增 cpr_metrics schemas 与派生指标计算函数"
```

---

### Task 4: Service 层重构

**Files:**
- Modify: `backend/app/services/exam_service.py`

- [ ] **Step 1: 重写 `backend/app/services/exam_service.py`**

```python
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.cpr_metrics import CprMetrics
from backend.app.models.event import ExamEvent
from backend.app.models.exam import Exam
from backend.app.models.score import ExamScore
from backend.app.schemas.cpr_metrics import CprMetricsUpload, derive_scoring_metrics
from backend.app.schemas.score import PhaseScore


async def create_exam(db: AsyncSession, device_code: str, video_path: str) -> Exam:
    """创建考试记录 - 以设备码作为归属键, user_id 设备直连场景留空"""
    exam = Exam(
        device_code=device_code,
        user_id=None,
        video_url=video_path,
        status="pending",
    )
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    return exam


async def get_exam(db: AsyncSession, exam_id: int) -> Exam | None:
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    return result.scalar_one_or_none()


async def update_exam_status(
    db: AsyncSession, exam_id: int, status: str, task_id: str | None = None
) -> None:
    exam = await get_exam(db, exam_id)
    if exam:
        exam.status = status
        if task_id:
            exam.task_id = task_id
        await db.flush()


async def upsert_cpr_metrics(
    db: AsyncSession,
    exam_id: int,
    device_code: str,
    payload: CprMetricsUpload,
) -> CprMetrics:
    """插入或更新 CPR 指标行 - 同时落原始计数与派生指标"""
    derived = derive_scoring_metrics(payload)
    existing = await db.execute(
        select(CprMetrics).where(CprMetrics.exam_id == exam_id)
    )
    row = existing.scalar_one_or_none()

    data = payload.model_dump()
    data.update(derived)
    data["device_code"] = device_code

    if row:
        for field, value in data.items():
            setattr(row, field, value)
    else:
        row = CprMetrics(exam_id=exam_id, **data)
        db.add(row)

    await db.flush()
    await db.refresh(row)
    return row


async def get_cpr_metrics(db: AsyncSession, exam_id: int) -> CprMetrics | None:
    result = await db.execute(
        select(CprMetrics).where(CprMetrics.exam_id == exam_id)
    )
    return result.scalar_one_or_none()


async def get_exam_result(db: AsyncSession, exam_id: int) -> dict:
    result = await db.execute(select(ExamScore).where(ExamScore.exam_id == exam_id))
    scores = result.scalars().all()

    exam = await get_exam(db, exam_id)
    total = sum(s.actual_score for s in scores)

    phase_map: dict[str, dict[str, float]] = defaultdict(
        lambda: {"score": 0.0, "max_score": 0.0}
    )
    for s in scores:
        phase_map[s.phase]["score"] += s.actual_score
        phase_map[s.phase]["max_score"] += s.max_score

    return {
        "exam_id": exam_id,
        "total_score": exam.total_score if exam else total,
        "max_total": 100.0,
        "items": scores,
        "phase_scores": {
            k: PhaseScore(score=v["score"], max_score=v["max_score"])
            for k, v in phase_map.items()
        },
    }


async def get_exam_timeline(db: AsyncSession, exam_id: int) -> list[ExamEvent]:
    result = await db.execute(
        select(ExamEvent)
        .where(ExamEvent.exam_id == exam_id)
        .order_by(ExamEvent.time_seconds)
    )
    return list(result.scalars().all())


async def list_exams_by_device(
    db: AsyncSession, device_code: str, skip: int = 0, limit: int = 20
) -> tuple[list[Exam], int]:
    """按设备码分页查询考试记录"""
    count_result = await db.execute(
        select(func.count())
        .select_from(Exam)
        .where(Exam.device_code == device_code)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Exam)
        .where(Exam.device_code == device_code)
        .order_by(Exam.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


def save_exam_events_sync(db_session, exam_id: int, events: list[dict]) -> None:
    for event in events:
        event_type = (
            event.get("event_type")
            or event.get("rule_code")
            or event.get("action")
            or "unknown"
        )
        if isinstance(event_type, str):
            event_type = event_type.strip() or "unknown"
        else:
            event_type = "unknown"

        db_event = ExamEvent(
            exam_id=exam_id,
            time_seconds=event.get("time", 0.0),
            actor=event.get("actor"),
            event_type=event_type,
            event_data=event.get("data"),
            source=event.get("source", "fusion"),
            confidence=event.get("confidence", 1.0),
        )
        db_session.add(db_event)
    db_session.flush()


def save_exam_scores_sync(db_session, exam_id: int, score_result: dict) -> None:
    for item in score_result.get("items", []):
        db_score = ExamScore(
            exam_id=exam_id,
            phase=item.get("phase", ""),
            rule_code=item.get("rule_code", ""),
            rule_name=item.get("rule_name", ""),
            max_score=item.get("max_score", 0.0),
            actual_score=item.get("actual_score", 0.0),
            deduction_reason=item.get("deduction_reason"),
            evidence_data=item.get("evidence"),
        )
        db_session.add(db_score)
    db_session.flush()
```

- [ ] **Step 2: Service 导入烟测**

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
python -c "from backend.app.services.exam_service import create_exam, upsert_cpr_metrics, list_exams_by_device, get_cpr_metrics; print('service ok')"
```

Expected: `service ok`

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: exam_service 改造 - device_code 归属键 + cpr_metrics CRUD"
```

---

### Task 5: 合并上传接口 + GET 接口去鉴权

**Files:**
- Modify: `backend/app/api/v1/exam.py`

- [ ] **Step 1: 完整重写 `backend/app/api/v1/exam.py`**

```python
import json
import random
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import get_async_db
from backend.app.schemas.cpr_metrics import (
    CprMetricsResponse,
    CprMetricsUpload,
    derive_scoring_metrics,
)
from backend.app.schemas.event import TimelineResponse
from backend.app.schemas.exam import (
    ExamListResponse,
    ExamStatusResponse,
    ExamUploadResponse,
)
from backend.app.schemas.score import ScoreResultResponse
from backend.app.services import exam_service
from backend.app.tasks.exam_task import process_exam_task

router = APIRouter(prefix="/exam", tags=["考试"])

# 允许上传的视频文件扩展名
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

# 满分 mock 指标 - 客观评分 40/40
PERFECT_MOCK_METRICS = {
    "session_duration_sec": 180.0,
    "compression_duration_sec": 150.0,
    "press_total": 200,
    "press_correct": 190,
    "press_wrong": 10,
    "press_frequency": 110.0,
    "press_avg_depth": 52.0,
    "blow_total": 20,
    "blow_correct": 19,
    "blow_wrong": 1,
    "blow_avg_volume": 540.0,
    "shoulder_tapped": True,
}


@router.post("/upload", response_model=ExamUploadResponse)
async def upload_exam(
    file: UploadFile = File(..., description="考试视频文件"),
    device_code: str = Form(..., min_length=1, max_length=64, description="设备唯一码"),
    metrics: str | None = Form(default=None, description="CPR 模拟人指标 JSON 字符串"),
    db: AsyncSession = Depends(get_async_db),
):
    """合并上传接口 - 视频文件 + 设备码 + CPR 指标(可选)一次性上报。"""
    # 校验文件扩展名
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}, 支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 解析 metrics(若提供)
    metrics_payload: CprMetricsUpload | None = None
    if metrics is not None and metrics.strip():
        try:
            metrics_dict = json.loads(metrics)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"metrics 字段非合法 JSON: {exc}",
            )
        try:
            metrics_payload = CprMetricsUpload(**metrics_dict)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"metrics 字段校验失败: {exc.errors()}",
            )

    # 准备上传目录 (绝对路径, api/celery_worker 共享挂载)
    upload_dir = Path(settings.upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = (upload_dir / filename).resolve()

    # 读取文件并校验大小
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大: {size_mb:.1f}MB, 最大允许: {settings.max_upload_size_mb}MB",
        )

    # 落盘
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(
        f"[上传] 视频已写入磁盘: path={file_path}, size={size_mb:.2f}MB, "
        f"device_code={device_code}, original_name={file.filename}"
    )

    # 创建考试记录
    exam = await exam_service.create_exam(db, device_code, str(file_path))
    await db.flush()

    # 若有 metrics 一并落库 (派生指标在 service 内计算)
    metrics_received = False
    if metrics_payload is not None:
        await exam_service.upsert_cpr_metrics(db, exam.id, device_code, metrics_payload)
        metrics_received = True
        logger.info(f"[上传] 已写入 cpr_metrics: exam_id={exam.id}")

    # 派发 Celery 任务
    task = process_exam_task.delay(exam.id, str(file_path))
    exam.task_id = task.id
    exam.status = "pending"
    await db.flush()

    logger.info(
        f"[上传] 已派发 Celery 任务: exam_id={exam.id}, task_id={task.id}, "
        f"device_code={device_code}, metrics_received={metrics_received}"
    )

    return ExamUploadResponse(
        exam_id=exam.id,
        task_id=task.id,
        device_code=device_code,
        metrics_received=metrics_received,
    )


@router.post("/mock-upload")
async def mock_upload(
    device_code: str = Form(..., min_length=1, max_length=64),
    perfect: bool = Query(default=True, description="是否生成满分指标"),
    db: AsyncSession = Depends(get_async_db),
):
    """调试用 - 不上传视频, 生成假 exam_id + mock 指标, 直接置为 completed 状态。"""
    if perfect:
        metrics_dict = dict(PERFECT_MOCK_METRICS)
    else:
        metrics_dict = {
            "session_duration_sec": round(random.uniform(120, 240), 1),
            "compression_duration_sec": round(random.uniform(80, 180), 1),
            "press_total": random.randint(100, 250),
            "press_correct": random.randint(70, 230),
            "press_wrong": random.randint(0, 30),
            "press_frequency": round(random.uniform(100, 120), 1),
            "press_avg_depth": round(random.uniform(45, 55), 1),
            "blow_total": random.randint(10, 30),
            "blow_correct": random.randint(7, 28),
            "blow_wrong": random.randint(0, 5),
            "blow_avg_volume": round(random.uniform(400, 600), 1),
            "shoulder_tapped": True,
        }

    metrics_payload = CprMetricsUpload(**metrics_dict)

    exam = await exam_service.create_exam(db, device_code, "<mock>/no-video.mp4")
    exam.status = "completed"
    await db.flush()
    await exam_service.upsert_cpr_metrics(db, exam.id, device_code, metrics_payload)

    derived = derive_scoring_metrics(metrics_payload)
    logger.info(
        f"[mock] 已生成 mock 考试记录: exam_id={exam.id}, device_code={device_code}, "
        f"derived={derived}"
    )

    return {
        "exam_id": exam.id,
        "device_code": device_code,
        "mock": True,
        "perfect": perfect,
        "derived_metrics": derived,
    }


@router.get("/{exam_id}/status", response_model=ExamStatusResponse)
async def get_exam_status(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """查询考试处理进度。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    progress = 0
    stage = None
    substep = None
    detail = None
    if exam.status == "completed":
        progress = 100
    elif exam.status == "processing" and exam.task_id:
        from backend.app.tasks.celery_app import celery_app

        result = celery_app.AsyncResult(exam.task_id)
        if result.state == "PROGRESS" and isinstance(result.info, dict):
            progress = result.info.get("progress", 0)
            stage = result.info.get("stage")
            substep = result.info.get("substep")
            detail = result.info.get("detail")

    return ExamStatusResponse(
        id=exam.id,
        status=exam.status,
        progress=progress,
        stage=stage,
        substep=substep,
        detail=detail,
    )


@router.get("/{exam_id}/result", response_model=ScoreResultResponse)
async def get_exam_result(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取考试评分结果。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    return await exam_service.get_exam_result(db, exam_id)


@router.get("/{exam_id}/timeline", response_model=TimelineResponse)
async def get_exam_timeline(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取考试事件时间轴。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    events = await exam_service.get_exam_timeline(db, exam_id)
    return TimelineResponse(events=events)


@router.get("/{exam_id}/metrics", response_model=CprMetricsResponse)
async def get_exam_metrics(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取该考试关联的 CPR 模拟人指标 (含派生评分指标)。"""
    row = await exam_service.get_cpr_metrics(db, exam_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="该考试无 CPR 指标"
        )
    return row


@router.get("/{exam_id}/video")
async def get_exam_processed_video(
    exam_id: int, db: AsyncSession = Depends(get_async_db)
):
    """下载 AI 标注后的视频文件。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成处理"
        )
    if not exam.processed_video_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="标注视频尚未生成, 请检查 AI 流水线日志",
        )

    # 数据库里既可能是绝对路径, 也可能是历史相对路径
    raw_path = Path(exam.processed_video_url)
    if raw_path.is_absolute():
        video_path = raw_path
    else:
        video_path = (Path(settings.output_dir) / raw_path).resolve()

    if not video_path.exists():
        logger.warning(
            f"[下载] 标注视频文件不存在: db={exam.processed_video_url}, "
            f"resolved={video_path}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注视频文件未找到: {video_path.name}",
        )

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"exam_{exam_id}_annotated.mp4",
    )


@router.get("/{exam_id}/debug")
async def get_exam_debug_data(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """调试数据接口: 返回转写文本、话术匹配、说话人角色"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )

    events = await exam_service.get_exam_timeline(db, exam_id)

    audio_events = [e for e in events if e.source == "audio"]
    transcription = []
    voice_matches = []
    speaker_roles = {}

    for e in audio_events:
        data = e.event_data or {}
        if e.event_type == "audio_transcript_segment":
            speaker = data.get("speaker")
            speaker_role = data.get("speaker_role") or "unknown"
            transcription.append(
                {
                    "start": data.get("start", e.time_seconds),
                    "end": data.get("end", e.time_seconds),
                    "text": data.get("text", ""),
                    "speaker": speaker,
                    "speaker_role": speaker_role,
                }
            )
            if speaker:
                speaker_roles[speaker] = speaker_role

        if data.get("matched_text"):
            voice_matches.append(
                {
                    "time": e.time_seconds,
                    "rule_code": e.event_type,
                    "rule_name": data.get("rule_name", ""),
                    "phase": data.get("phase", ""),
                    "score": data.get("score", 0),
                    "similarity": data.get("similarity", 0),
                    "matched_text": data.get("matched_text", ""),
                    "matched_template": data.get("matched_template", ""),
                    "speaker": e.actor,
                    "speaker_role": data.get("speaker_role"),
                    "role_correct": data.get("role_correct", True),
                }
            )

    return {
        "transcription": transcription,
        "voice_matches": voice_matches,
        "speaker_roles": speaker_roles,
    }


@router.get("/{exam_id}/report")
async def get_exam_report(exam_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取 HTML 格式的考试评分报告。"""
    exam = await exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="考试记录不存在"
        )
    if exam.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="考试尚未完成评分"
        )

    from fastapi.responses import HTMLResponse

    from backend.app.services.report_service import generate_html_report

    score_data = await exam_service.get_exam_result(db, exam_id)
    html = generate_html_report(
        exam_id=exam_id,
        score_result=score_data,
        created_at=str(exam.created_at),
    )

    return HTMLResponse(content=html)


@router.get("s", response_model=ExamListResponse)
async def list_exams(
    device_code: str = Query(..., min_length=1, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    """按设备码分页获取考试记录列表。"""
    skip = (page - 1) * page_size
    items, total = await exam_service.list_exams_by_device(
        db, device_code, skip, page_size
    )
    return ExamListResponse(items=items, total=total)
```

- [ ] **Step 2: 添加 `python-multipart` 依赖检查**

FastAPI 接收 `Form/File` 需要 `python-multipart`。检查是否已存在:

```bash
grep -i "multipart" /Users/allen/Code/algorithmCode/Emergency-AI-Examiner/backend/requirements.txt
```

若无,追加 `python-multipart>=0.0.6` 到 `backend/requirements.txt` 末尾。

- [ ] **Step 3: 启动 uvicorn 烟测**

注意:由于数据库结构已变,本地直接启动可能与本地 dev DB 不兼容。先用 Python 跑导入烟测验证语法:

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
python -c "from backend.app.api.v1.exam import router; print('exam router ok, routes:', [r.path for r in router.routes])"
```

Expected 输出含 `/exam/upload`、`/exam/mock-upload`、`/exam/{exam_id}/metrics`、`/exams` 等路径。

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
python -c "from backend.app.main import app; print('app ok, routes:', len(app.routes))"
```

Expected: `app ok, routes: <N>`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: 合并 /exam/upload 接口 - multipart 一次上报视频+设备码+指标"
```

---

### Task 6: Celery 任务读 cpr_metrics

**Files:**
- Modify: `backend/app/tasks/exam_task.py:80-91`

- [ ] **Step 1: 替换 `exam_task.py` 中"查询关联的传感器数据"代码段**

定位 `backend/app/tasks/exam_task.py` 第 79-91 行,把:

```python
        # 查询关联的传感器数据 (CPR 模拟人数据, 可选)
        from backend.app.models.sensor import SensorData

        sensor_row = db.query(SensorData).filter(SensorData.exam_id == exam_id).first()
        sensor_dict = None
        if sensor_row:
            sensor_dict = {
                "compression_compliance_rate": sensor_row.compression_compliance_rate,
                "ventilation_compliance_rate": sensor_row.ventilation_compliance_rate,
                "ccf_percentage": sensor_row.ccf_percentage,
            }
            logger.info(f"[考试 {exam_id}] 已加载传感器数据: {sensor_dict}")
```

替换为:

```python
        # 查询关联的 CPR 指标 (设备上报, 可选)
        from backend.app.models.cpr_metrics import CprMetrics

        metrics_row = (
            db.query(CprMetrics).filter(CprMetrics.exam_id == exam_id).first()
        )
        sensor_dict = None
        if metrics_row:
            sensor_dict = {
                # 派生指标 - 现有评分规则消费
                "compression_compliance_rate": metrics_row.compression_compliance_rate,
                "ventilation_compliance_rate": metrics_row.ventilation_compliance_rate,
                "ccf_percentage": metrics_row.ccf_percentage,
                # 原始计数透传 - 后续若新增更细粒度评分规则可直接使用
                "press_total": metrics_row.press_total,
                "press_correct": metrics_row.press_correct,
                "blow_total": metrics_row.blow_total,
                "blow_correct": metrics_row.blow_correct,
            }
            logger.info(f"[考试 {exam_id}] 已加载 CPR 指标: {sensor_dict}")
```

- [ ] **Step 2: 任务模块导入烟测**

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
python -c "from backend.app.tasks.exam_task import process_exam_task; print('celery task ok:', process_exam_task.name)"
```

Expected: `celery task ok: backend.app.tasks.exam_task.process_exam_task`

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: Celery 任务从 cpr_metrics 表读取派生指标"
```

---

### Task 7: 清理 main.py 与未使用导入

**Files:**
- Modify: `backend/app/main.py:11`

- [ ] **Step 1: 修改 `backend/app/main.py` 第 11 行**

将:

```python
from backend.app.models import Exam, ExamEvent, ExamScore, User  # noqa: F401
```

替换为:

```python
from backend.app.models import CprMetrics, Exam, ExamEvent, ExamScore  # noqa: F401
```

`User` 模型仍在 `backend/app/models/user.py`,但 `main.py` 中不再需要直接引用(SQLAlchemy 元数据已通过 `backend.app.models.__init__` 自动注册所有模型)。`CprMetrics` 显式 import 是为了确保 `Base.metadata.create_all` 看到新表。

- [ ] **Step 2: 启动应用烟测**

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
python -c "from backend.app.main import app; print('app ok')"
```

Expected: `app ok`

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
ruff check backend/ 2>&1 | head -20
```

Expected: 无 F401 / 未使用 import 报错(如有 ruff 报错,按提示修正)。

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: main.py 替换 User 为 CprMetrics 元数据注册"
```

---

### Task 8: 数据库重置脚本

**Files:**
- Create: `scripts/reset_db.sh`

- [ ] **Step 1: 创建 `scripts/reset_db.sh`**

```bash
#!/usr/bin/env bash
# ============================================================================
# 数据库重置脚本 - 删除所有业务表, 让后端启动时自动重建
#
# 适用场景: 表结构破坏性变更 (本次设备直连改造 = 用此脚本)
# 不动: db_data 卷本身、postgres 用户/角色
#
# 使用方式:
#   ./scripts/reset_db.sh              # 在本机 docker 上执行 (本地开发)
#   REMOTE=1 ./scripts/reset_db.sh     # ssh 192.168.31.82 上执行
#
# 环境变量:
#   DEPLOY_HOST  远端主机, 默认 192.168.31.82
#   DEPLOY_USER  远端 SSH 用户, 默认 root
#   DEPLOY_DIR   远端代码目录, 默认 /data/sdb/Emergency-AI-Examiner
# ============================================================================

set -euo pipefail

REMOTE="${REMOTE:-0}"
REMOTE_HOST="${DEPLOY_HOST:-192.168.31.82}"
REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE_DIR="${DEPLOY_DIR:-/data/sdb/Emergency-AI-Examiner}"

# 注意删除顺序: 先删带外键的子表, 再删主表
SQL=$(cat <<'EOF'
DROP TABLE IF EXISTS exam_scores CASCADE;
DROP TABLE IF EXISTS exam_events CASCADE;
DROP TABLE IF EXISTS speaker_role_maps CASCADE;
DROP TABLE IF EXISTS transcripts CASCADE;
DROP TABLE IF EXISTS cpr_metrics CASCADE;
DROP TABLE IF EXISTS sensor_data CASCADE;
DROP TABLE IF EXISTS exams CASCADE;
DROP TABLE IF EXISTS users CASCADE;
EOF
)

echo "==> 将执行以下 SQL:"
echo "${SQL}"
echo

if [[ "${REMOTE}" == "1" ]]; then
  echo "==> 在远端 ${REMOTE_USER}@${REMOTE_HOST} 上执行..."
  ssh "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker exec -i examiner_db psql -U postgres -d emergency_examiner" <<< "${SQL}"
else
  echo "==> 在本地 docker 上执行..."
  docker exec -i examiner_db psql -U postgres -d emergency_examiner <<< "${SQL}"
fi

echo "==> 数据库已重置, 重启后端会自动重建新表结构"
```

- [ ] **Step 2: 加可执行权限**

```bash
chmod +x scripts/reset_db.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/reset_db.sh
git commit -m "tooling: 新增 reset_db.sh - 表结构破坏性变更时重置库"
```

---

### Task 9: 设备 API 对接文档

**Files:**
- Create: `docs/device_api.md`

- [ ] **Step 1: 创建 `docs/device_api.md`**

```markdown
# 设备直连对接文档

> 面向 CPR 模拟人设备工程师, 描述如何将考试视频与传感器指标上报到院前急救自动考核系统。
> Last update: 2026-05-28

---

## 1. 基本信息

- **BaseURL (远端测试)**: `http://192.168.31.82:8001`
- **BaseURL (生产)**: 待运维提供
- **协议**: HTTP/1.1
- **无鉴权**: 不需要 token, 设备直连即可调用
- **字符集**: UTF-8

### 错误响应格式

所有错误以 FastAPI 标准格式返回:

```json
{ "detail": "<中文错误说明>" }
```

| HTTP Code | 含义 |
|---|---|
| 400 | 参数错误(扩展名/JSON/字段范围) |
| 404 | 资源不存在(exam_id 无效) |
| 413 | 文件过大(默认上限 2GB) |
| 500 | 服务器错误(落盘/数据库异常) |

---

## 2. 上报接口

### POST `/api/v1/exam/upload`

合并上传 - 一次性提交考试视频 + 设备码 + CPR 模拟人指标(可选)。

**请求**

- Content-Type: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | 是 | 考试视频, 支持 .mp4/.mov/.avi/.mkv/.webm, ≤ 2GB |
| `device_code` | string | 是 | 设备唯一码, 1-64 字符 |
| `metrics` | string (JSON) | 否 | CPR 指标 JSON 字符串, 无模拟人时可省略 |

**响应 200**

```json
{
  "exam_id": 42,
  "task_id": "8c4f9a-...",
  "device_code": "DEV-001",
  "metrics_received": true,
  "status": "pending"
}
```

**curl 示例**

```bash
curl -X POST http://192.168.31.82:8001/api/v1/exam/upload \
  -F "file=@/path/to/exam.mp4" \
  -F "device_code=DEV-001" \
  -F 'metrics={"session_duration_sec":180,"compression_duration_sec":145,"press_total":200,"press_correct":185,"press_wrong":15,"press_frequency":112,"press_avg_depth":53,"blow_total":20,"blow_correct":18,"blow_wrong":2}'
```

**Java OkHttp 示例**

```java
OkHttpClient client = new OkHttpClient();

String metricsJson = new Gson().toJson(metricsMap);

RequestBody body = new MultipartBody.Builder()
    .setType(MultipartBody.FORM)
    .addFormDataPart("file", "exam.mp4",
        RequestBody.create(MediaType.parse("video/mp4"), videoFile))
    .addFormDataPart("device_code", "DEV-001")
    .addFormDataPart("metrics", metricsJson)
    .build();

Request request = new Request.Builder()
    .url("http://192.168.31.82:8001/api/v1/exam/upload")
    .post(body)
    .build();

Response response = client.newCall(request).execute();
```

---

## 3. `metrics` JSON 字段定义

> 字段命名规范: 蛇形小写 (snake_case)。设备端 CPRData.java 字段为驼峰 (camelCase), 上报前需做命名转换。
> 所有计数字段非负; 浮点字段单位见下表。

### 3.1 会话时长 (用于派生 CCF)

| 字段 | 类型 | 必填 | 单位 | 说明 |
|---|---|---|---|---|
| `session_duration_sec` | float | 是 | 秒 | 考试总时长 |
| `compression_duration_sec` | float | 是 | 秒 | 有按压动作的累计时长 |

### 3.2 按压核心计数

| 字段 | 类型 | 必填 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|---|
| `press_total` | int | 是 | 次 | `pressNubmer` | 按压总次数 |
| `press_correct` | int | 是 | 次 | `pressRightNumber` | 按压正确次数 |
| `press_wrong` | int | 是 | 次 | `pressWrongNumber` | 按压错误次数 |
| `press_frequency` | float | 是 | 次/分 | `pressFrequency` | 平均按压频率 |
| `press_avg_depth` | float | 是 | mm | 聚合自 `pressValue` 序列 | 平均按压深度 |

### 3.3 按压错误分布(可选, 默认 0)

| 字段 | 类型 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|
| `press_too_deep` | int | 次 | `pressOversize` | 按压过深次数 |
| `press_too_shallow` | int | 次 | `pressSmall` | 按压过浅次数 |
| `press_too_fast` | int | 次 | `pressMore` | 按压过快次数 |
| `press_too_slow` | int | 次 | `pressLow` | 按压过慢次数 |
| `press_no_recoil` | int | 次 | `pressNoSet` | 未回弹次数 |
| `press_wrong_position` | int | 次 | `pressPositionWrong` | 位置错误次数 |

### 3.4 通气核心计数

| 字段 | 类型 | 必填 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|---|
| `blow_total` | int | 是 | 次 | `blowNumber` | 通气总次数 |
| `blow_correct` | int | 是 | 次 | `blowRightNumber` | 通气正确次数 |
| `blow_wrong` | int | 是 | 次 | `blowWrongNumber` | 通气错误次数 |
| `blow_avg_volume` | float | 否 | ml | 聚合自 `blowValue` | 平均通气量 |

### 3.5 通气错误分布(可选, 默认 0)

| 字段 | 类型 | 单位 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|
| `blow_too_much` | int | 次 | `blowOversize` | 通气过多次数 |
| `blow_too_little` | int | 次 | `blowSmall` | 通气过少次数 |
| `blow_too_many` | int | 次 | `blowMore` | 多吹次数 |
| `blow_too_few` | int | 次 | `blowLow` | 少吹次数 |
| `blow_into_stomach` | int | 次 | 累计 `isBlowStomach=true` | 进胃次数 |
| `blow_airway_blocked` | int | 次 | 累计 `isBlowWayIn=false` | 气道未开放次数 |

### 3.6 流程

| 字段 | 类型 | 必填 | 对应 CPRData.java | 说明 |
|---|---|---|---|---|
| `shoulder_tapped` | bool | 否 | `clap_your_shoulders` | 是否完成拍肩(默认 false) |

### 3.7 字段填写边界

- 没有进行按压的会话: `press_total = 0`、`press_correct = 0`、其余按压字段都填 0
- 没有进行通气的会话: `blow_total = 0`、`blow_correct = 0`、其余通气字段都填 0
- `session_duration_sec` 必须 > 0,否则 CCF 派生为 0
- 完全没有 CPR 模拟人时,**整个 `metrics` 字段可省略**,服务器会按视频估算 CCF

---

## 4. 服务器派生指标公式

服务器接收到 `metrics` 后,会自动派生以下三个评分用指标并入库:

| 派生字段 | 公式 | 说明 |
|---|---|---|
| `compression_compliance_rate` | `press_correct / press_total * 100` | 按压达标率(%),分母 0 时记 0 |
| `ventilation_compliance_rate` | `blow_correct / blow_total * 100` | 通气达标率(%),分母 0 时记 0 |
| `ccf_percentage` | `compression_duration_sec / session_duration_sec * 100` | 胸外按压比 CCF(%),分母 0 时记 0 |

**评分规则(客观分 40/40)**

| 项目 | 计算 | 满分 |
|---|---|---|
| 按压质量 | `compression_compliance_rate ≥ 90 → 10`, 否则 `10 × rate/90` | 10 |
| 通气质量 | `ventilation_compliance_rate ≥ 90 → 10`, 否则 `10 × rate/90` | 10 |
| CCF 评分 | `min(20 × ccf/80, 20)` | 20 |

---

## 5. 查询接口

### 5.1 GET `/api/v1/exam/{exam_id}/status`

轮询考试处理进度。

**响应 200**

```json
{
  "id": 42,
  "status": "processing",
  "progress": 65,
  "stage": "scoring",
  "substep": "fusion",
  "detail": null
}
```

`status` 可能值: `pending` / `processing` / `completed` / `failed`。建议每 2-5 秒轮询一次直到 `completed` 或 `failed`。

### 5.2 GET `/api/v1/exam/{exam_id}/result`

获取最终评分(仅 `status=completed` 可用)。

**响应 200**

```json
{
  "exam_id": 42,
  "total_score": 87.5,
  "max_total": 100.0,
  "items": [...],
  "phase_scores": {...}
}
```

### 5.3 GET `/api/v1/exam/{exam_id}/metrics`

回显该考试的 CPR 指标 + 派生指标(供设备端确认上报无误)。

### 5.4 GET `/api/v1/exam/{exam_id}/report`

返回 HTML 评分报告,可直接浏览器打开。

### 5.5 GET `/api/v1/exam/{exam_id}/video`

下载 AI 标注后的视频文件(含姿态骨架与字幕)。

### 5.6 GET `/api/v1/exams?device_code=DEV-001&page=1&page_size=20`

按设备码分页查询考试列表。

---

## 6. 调试接口

### POST `/api/v1/exam/mock-upload?perfect=true`

不上传视频, 直接生成 mock 满分(或随机)考试记录, 用于设备端联调。

**Form 字段**: `device_code` (必填)

**Query 参数**: `perfect=true|false`(默认 true)

**响应 200**

```json
{
  "exam_id": 99,
  "device_code": "DEV-001",
  "mock": true,
  "perfect": true,
  "derived_metrics": {
    "compression_compliance_rate": 95.0,
    "ventilation_compliance_rate": 95.0,
    "ccf_percentage": 83.33
  }
}
```

---

## 7. 联系方式

线上 Swagger UI: `http://192.168.31.82:8001/docs`
如字段或接口与文档不一致,以 Swagger 为准并联系后端工程师。
```

- [ ] **Step 2: Commit**

```bash
git add docs/device_api.md
git commit -m "docs: 新增设备工程师对接文档 device_api.md"
```

---

### Task 10: 端到端验收

**Files:**(无,仅运行验证)

- [ ] **Step 1: 部署到远端 192.168.31.82**

```bash
cd /Users/allen/Code/algorithmCode/Emergency-AI-Examiner
./scripts/deploy.sh rebuild
```

Expected: deploy 成功,远端 `docker compose ps` 显示 api/celery_worker 均为 healthy。

- [ ] **Step 2: 远端重置数据库(本次破坏性结构变更必须执行一次)**

```bash
REMOTE=1 ./scripts/reset_db.sh
```

Expected: SQL 执行无错误,所有 DROP TABLE 完成。

- [ ] **Step 3: 重启 api 让新表生效**

```bash
ssh root@192.168.31.82 "cd /data/sdb/Emergency-AI-Examiner && docker compose restart api"
```

- [ ] **Step 4: 检查 Swagger 路由清单**

浏览器打开 `http://192.168.31.82:8001/docs`,确认:
- 有 `/api/v1/exam/upload`、`/api/v1/exam/mock-upload`、`/api/v1/exam/{exam_id}/metrics`
- 没有 `/api/v1/auth/*` 与 `/api/v1/sensor/*`

- [ ] **Step 5: mock-upload 验证(快路径,不需要视频)**

```bash
curl -X POST "http://192.168.31.82:8001/api/v1/exam/mock-upload?perfect=true" \
  -F "device_code=DEV-001"
```

Expected: 返回 `exam_id`、`derived_metrics` 三个比例均 ≥ 80。

- [ ] **Step 6: 用返回的 exam_id 验 metrics 回显**

```bash
curl http://192.168.31.82:8001/api/v1/exam/<exam_id>/metrics | python -m json.tool
```

Expected: 返回完整 CPR 指标 + 三个派生指标。

- [ ] **Step 7: 列表接口验证**

```bash
curl "http://192.168.31.82:8001/api/v1/exams?device_code=DEV-001"
```

Expected: 返回 items 数组,含上一步生成的 exam。

- [ ] **Step 8: 真实视频上传验证(慢路径,可选)**

```bash
curl -X POST http://192.168.31.82:8001/api/v1/exam/upload \
  -F "file=@/path/to/exam.mp4" \
  -F "device_code=DEV-001" \
  -F 'metrics={"session_duration_sec":180,"compression_duration_sec":145,"press_total":200,"press_correct":185,"press_wrong":15,"press_frequency":112,"press_avg_depth":53,"blow_total":20,"blow_correct":18,"blow_wrong":2}'
```

Expected: 返回 200 + exam_id + task_id;轮询 `/exam/{id}/status` 直到 completed;`/exam/{id}/result` 含按压/通气/CCF 三项客观分。

- [ ] **Step 9: 验收完成提交**

不需要新 commit,本任务仅验证。若发现 bug 回到对应 Task 修复并提交修复 commit。

---

## 验收标准

完成 Task 10 全部步骤后,应满足:

1. Swagger 显示合并接口与新增 metrics 接口,无 auth/sensor 路由
2. mock-upload 接口可独立验证派生指标计算正确
3. 真实视频上传 → Celery 任务 → 评分入库的端到端链路打通
4. `GET /api/v1/exams?device_code=` 仅返回该设备的考试记录
5. `docs/device_api.md` 可独立分发给设备工程师
