from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1.router import api_v1_router
from backend.app.config import settings
from backend.app.database import Base, async_engine
from backend.app.models import Exam, ExamEvent, ExamScore, User  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield
    await async_engine.dispose()


app = FastAPI(
    title="Emergency-AI-Examiner",
    description="院前急救自动考核评分系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)

upload_path = Path(settings.upload_dir)
if upload_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(upload_path)), name="uploads")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Emergency-AI-Examiner"}
