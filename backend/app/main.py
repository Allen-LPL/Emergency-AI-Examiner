from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import text

from backend.app.api.v1.router import api_v1_router
from backend.app.config import settings
from backend.app.database import Base, async_engine
from backend.app.models import CprMetrics, Exam, ExamEvent, ExamScore  # noqa: F401

# 启动时需要补齐的列 (幂等 ALTER TABLE IF NOT EXISTS, 兼容已有部署)
# create_all 只能建表, 无法为已存在表追加列, 这里集中收口存量库的小迁移
_BOOTSTRAP_COLUMN_MIGRATIONS: list[str] = [
    "ALTER TABLE exams ADD COLUMN IF NOT EXISTS report_pdf_url VARCHAR(500)",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保上传目录与标注视频输出目录均存在 (绑定挂载场景下也保证容器侧路径可写)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 幂等执行存量库的列补齐, 避免老库少字段导致 SELECT 报 UndefinedColumn
        for ddl in _BOOTSTRAP_COLUMN_MIGRATIONS:
            try:
                await conn.execute(text(ddl))
                logger.info(f"[启动] 列迁移执行成功: {ddl}")
            except Exception as exc:
                # IF NOT EXISTS 已保证幂等, 这里仅兜底打印不阻塞启动
                logger.warning(f"[启动] 列迁移执行失败 (已忽略, 不影响启动): {ddl} | {exc}")

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
