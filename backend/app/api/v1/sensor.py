import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_async_db
from backend.app.models.sensor import SensorData
from backend.app.schemas.sensor import SensorDataResponse, SensorDataUpload

router = APIRouter(prefix="/sensor", tags=["传感器数据"])


@router.post("/upload", response_model=SensorDataResponse)
async def upload_sensor_data(
    payload: SensorDataUpload,
    db: AsyncSession = Depends(get_async_db),
):
    existing = await db.execute(
        select(SensorData).where(SensorData.exam_id == payload.exam_id)
    )
    row = existing.scalar_one_or_none()

    if row:
        for field, value in payload.model_dump(exclude={"exam_id"}).items():
            setattr(row, field, value)
    else:
        row = SensorData(**payload.model_dump())
        db.add(row)

    await db.flush()
    await db.refresh(row)
    return row


@router.post("/mock/{exam_id}", response_model=SensorDataResponse)
async def generate_mock_sensor(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    existing = await db.execute(select(SensorData).where(SensorData.exam_id == exam_id))
    row = existing.scalar_one_or_none()

    mock = {
        "compression_compliance_rate": round(random.uniform(75, 95), 1),
        "ventilation_compliance_rate": round(random.uniform(70, 90), 1),
        "ccf_percentage": round(random.uniform(60, 80), 1),
        "avg_compression_depth": round(random.uniform(45, 55), 1),
        "avg_compression_rate": round(random.uniform(100, 120), 1),
        "total_compressions": random.randint(500, 1500),
        "total_ventilations": random.randint(20, 60),
    }

    if row:
        for field, value in mock.items():
            setattr(row, field, value)
    else:
        row = SensorData(exam_id=exam_id, **mock)
        db.add(row)

    await db.flush()
    await db.refresh(row)
    return row


@router.get("/{exam_id}", response_model=SensorDataResponse)
async def get_sensor_data(
    exam_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(SensorData).where(SensorData.exam_id == exam_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该考试无传感器数据",
        )
    return row
