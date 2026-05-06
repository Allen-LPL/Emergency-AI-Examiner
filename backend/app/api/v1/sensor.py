import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_async_db
from backend.app.models.sensor import SensorData
from backend.app.schemas.sensor import SensorDataResponse, SensorDataUpload

router = APIRouter(prefix="/sensor", tags=["传感器数据"])

# 满分 mock 数据 — 对应客观评分 40/40
# 按压达标率 ≥90% → 10/10, 通气达标率 ≥90% → 10/10, CCF ≥80% → 20/20
PERFECT_SCORE_MOCK = {
    "compression_compliance_rate": 95.0,
    "ventilation_compliance_rate": 92.0,
    "ccf_percentage": 82.0,
    "avg_compression_depth": 52.0,
    "avg_compression_rate": 110.0,
    "total_compressions": 1200,
    "total_ventilations": 40,
}


async def _upsert_sensor(db: AsyncSession, exam_id: int, data: dict) -> SensorData:
    """插入或更新传感器数据，返回数据库行。"""
    existing = await db.execute(select(SensorData).where(SensorData.exam_id == exam_id))
    row = existing.scalar_one_or_none()

    if row:
        for field, value in data.items():
            setattr(row, field, value)
    else:
        row = SensorData(exam_id=exam_id, **data)
        db.add(row)

    await db.flush()
    await db.refresh(row)
    return row


@router.post("/upload", response_model=SensorDataResponse)
async def upload_sensor_data(
    payload: SensorDataUpload,
    db: AsyncSession = Depends(get_async_db),
):
    """
    上传 CPR 模拟人传感器数据。

    用于接收 CPR 训练模拟人的实时质量数据，关联到指定的考试记录。
    若该考试已有传感器数据则更新，否则新建。

    **请求体字段说明:**

    | 字段 | 类型 | 范围 | 说明 |
    |---|---|---|---|
    | exam_id | int | >0 | 关联的考试记录 ID |
    | compression_compliance_rate | float | 0-100 | 按压达标率(%)，≥90% 得满分 |
    | ventilation_compliance_rate | float | 0-100 | 通气达标率(%)，≥90% 得满分 |
    | ccf_percentage | float | 0-100 | 胸外按压比例 CCF(%)，≥80% 得满分 |
    | avg_compression_depth | float? | mm | 平均按压深度，AHA 标准 50-60mm |
    | avg_compression_rate | float? | 次/分 | 平均按压频率，AHA 标准 100-120 次/分 |
    | total_compressions | int? | - | 总按压次数 |
    | total_ventilations | int? | - | 总通气次数 |

    **评分规则 (客观评分 40 分):**
    - 按压质量: `compression_compliance_rate ≥ 90` → 10/10 分
    - 通气质量: `ventilation_compliance_rate ≥ 90` → 10/10 分
    - CCF 评分: `min(20 × ccf_percentage / 80, 20)` → 最高 20/20 分
    """
    data = payload.model_dump(exclude={"exam_id"})
    row = await _upsert_sensor(db, payload.exam_id, data)
    return row


@router.post("/mock/{exam_id}", response_model=SensorDataResponse)
async def generate_mock_sensor(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """
    生成随机 mock 传感器数据（用于开发调试）。

    随机生成一组 CPR 质量指标并关联到指定考试，数据范围接近正常表现但不保证满分。
    若需要满分数据请使用 `POST /sensor/mock-perfect/{exam_id}`。
    """
    mock = {
        "compression_compliance_rate": round(random.uniform(75, 95), 1),
        "ventilation_compliance_rate": round(random.uniform(70, 90), 1),
        "ccf_percentage": round(random.uniform(60, 80), 1),
        "avg_compression_depth": round(random.uniform(45, 55), 1),
        "avg_compression_rate": round(random.uniform(100, 120), 1),
        "total_compressions": random.randint(500, 1500),
        "total_ventilations": random.randint(20, 60),
    }
    row = await _upsert_sensor(db, exam_id, mock)
    return row


@router.post("/mock-perfect/{exam_id}", response_model=SensorDataResponse)
async def generate_perfect_mock_sensor(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """
    生成满分 mock 传感器数据（客观评分 40/40 分）。

    写入一组满足所有评分满分阈值的固定数据，用于前端联调和端到端测试。

    **满分阈值:**
    - `compression_compliance_rate`: 95.0% (≥90% 即满分)
    - `ventilation_compliance_rate`: 92.0% (≥90% 即满分)
    - `ccf_percentage`: 82.0% (≥80% 即满分, 公式 `20×82/80=20.5` 封顶 20)
    - `avg_compression_depth`: 52.0 mm (AHA 标准 50-60mm)
    - `avg_compression_rate`: 110.0 次/分 (AHA 标准 100-120)
    - `total_compressions`: 1200 次
    - `total_ventilations`: 40 次

    **响应示例:**
    ```json
    {
        "id": 1,
        "exam_id": 42,
        "compression_compliance_rate": 95.0,
        "ventilation_compliance_rate": 92.0,
        "ccf_percentage": 82.0,
        "avg_compression_depth": 52.0,
        "avg_compression_rate": 110.0,
        "total_compressions": 1200,
        "total_ventilations": 40
    }
    ```
    """
    row = await _upsert_sensor(db, exam_id, dict(PERFECT_SCORE_MOCK))
    return row


@router.get("/{exam_id}", response_model=SensorDataResponse)
async def get_sensor_data(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """
    查询指定考试的传感器数据。

    返回关联的 CPR 模拟人传感器质量数据。若无数据返回 404。
    """
    result = await db.execute(select(SensorData).where(SensorData.exam_id == exam_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该考试无传感器数据",
        )
    return row
