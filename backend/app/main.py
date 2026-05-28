from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1.router import api_v1_router
from backend.app.config import settings
from backend.app.database import Base, async_engine
from backend.app.models import CprMetrics, Exam, ExamEvent, ExamScore  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保上传目录与标注视频输出目录均存在 (绑定挂载场景下也保证容器侧路径可写)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

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

# 静态资源挂载: /uploads 暴露原始视频, /outputs 暴露 AI 标注后的视频
# 标注视频由 celery_worker 容器写入 ./outputs (绑定挂载), api 容器即时可读
upload_path = Path(settings.upload_dir)
upload_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_path)), name="uploads")

output_path = Path(settings.output_dir)
output_path.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(output_path)), name="outputs")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Emergency-AI-Examiner"}
