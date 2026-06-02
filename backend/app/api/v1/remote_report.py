"""远端考核中心上报相关 API

提供两类运维接口, 用于排查 / 补传 Celery 任务漏掉的 exam 数据:
    - POST /remote-report/exam/{exam_id}: 单条手动重报
    - POST /remote-report/batch:           批量补传 exams 表数据

调用模型一律是同步 DB + 同步 httpx, 在 FastAPI 异步路由里通过
`run_in_threadpool` 转线程执行, 避免阻塞事件循环.
"""

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from loguru import logger
from pydantic import BaseModel, Field

from backend.app.database import sync_session_factory
from backend.app.services.remote_report_service import (
    BatchResult,
    ReportOutcome,
    batch_post_evaluations_sync,
    post_evaluation_for_exam_sync,
)

router = APIRouter(prefix="/remote-report", tags=["远端考核中心上报"])


class BatchReportRequest(BaseModel):
    """批量上报请求体 - 两种模式互斥, 优先按 exam_ids 走"""

    exam_ids: list[int] | None = Field(
        default=None,
        description="指定要上报的 exam_id 列表; 为空则全表扫描",
    )
    only_completed: bool = Field(
        default=True,
        description="全表扫描时, 是否仅取 status='completed' 的记录",
    )
    limit: int | None = Field(
        default=500,
        ge=1,
        le=10000,
        description="一次最多上报多少条, 防止误触全表跑挂 worker; 仅全表扫描时生效",
    )


class ReportOutcomeResponse(BaseModel):
    exam_id: int
    ok: bool
    status_code: int | None = None
    response_body: str = ""
    error: str = ""

    @classmethod
    def from_dc(cls, o: ReportOutcome) -> "ReportOutcomeResponse":
        return cls(
            exam_id=o.exam_id,
            ok=o.ok,
            status_code=o.status_code,
            response_body=o.response_body,
            error=o.error,
        )


class BatchReportResponse(BaseModel):
    total: int
    success: int
    failed: int
    skipped: int
    outcomes: list[ReportOutcomeResponse]

    @classmethod
    def from_dc(cls, r: BatchResult) -> "BatchReportResponse":
        return cls(
            total=r.total,
            success=r.success,
            failed=r.failed,
            skipped=r.skipped,
            outcomes=[ReportOutcomeResponse.from_dc(o) for o in r.outcomes],
        )


def _run_single(exam_id: int) -> ReportOutcome:
    """sync 包装: 起一个 sync session, 执行单条上报后关闭"""
    session = sync_session_factory()
    try:
        return post_evaluation_for_exam_sync(session, exam_id)
    finally:
        session.close()


def _run_batch(req: BatchReportRequest) -> BatchResult:
    """sync 包装: 起一个 sync session, 跑完整批后关闭"""
    session = sync_session_factory()
    try:
        return batch_post_evaluations_sync(
            session,
            exam_ids=req.exam_ids,
            only_completed=req.only_completed,
            limit=req.limit,
        )
    finally:
        session.close()


@router.post("/exam/{exam_id}", response_model=ReportOutcomeResponse)
async def report_single_exam(exam_id: int):
    """手动触发单条 exam 重报 - 主要给运维和联调排查用."""
    logger.info(f"[远端上报-API] 触发单条上报: exam_id={exam_id}")
    outcome = await run_in_threadpool(_run_single, exam_id)
    if outcome.error == "exam_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"exam_id={exam_id} 不存在",
        )
    return ReportOutcomeResponse.from_dc(outcome)


@router.post("/batch", response_model=BatchReportResponse)
async def report_batch_exams(
    req: BatchReportRequest = Body(default_factory=BatchReportRequest),
):
    """批量补传 exams 表数据到远端考核中心.

    典型用法:
        - 不传 body / 传 {}: 默认补传所有 status=completed 的最近 500 条
        - 指定 exam_ids: 只重报这些 (常用于失败重试)

    所有结果会同步落容器日志 (前缀 [远端上报]), 也会作为响应回写, 方便前端确认.
    """
    logger.info(
        f"[远端上报-API] 触发批量上报: exam_ids={req.exam_ids}, "
        f"only_completed={req.only_completed}, limit={req.limit}"
    )
    result = await run_in_threadpool(_run_batch, req)
    return BatchReportResponse.from_dc(result)
