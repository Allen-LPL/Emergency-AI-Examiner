# backend/app/api/v1/router.py
from fastapi import APIRouter

from backend.app.api.v1.exam import router as exam_router
from backend.app.api.v1.remote_report import router as remote_report_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(exam_router)
api_v1_router.include_router(remote_report_router)
