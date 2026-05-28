# backend/app/api/v1/router.py
from fastapi import APIRouter

from backend.app.api.v1.exam import router as exam_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(exam_router)
