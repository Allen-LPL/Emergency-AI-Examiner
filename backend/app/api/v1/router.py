from fastapi import APIRouter

from backend.app.api.v1.exam import router as exam_router
from backend.app.api.v1.sensor import router as sensor_router
from backend.app.api.v1.user import router as user_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(user_router)
api_v1_router.include_router(exam_router)
api_v1_router.include_router(sensor_router)
