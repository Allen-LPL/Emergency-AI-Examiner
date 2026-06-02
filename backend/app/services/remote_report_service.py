"""远端考核中心数据上报 service

集中收口本服务向远端 `evaluation-add` 接口的所有数据上报路径:
    1. Celery 评分任务结束后单条上报 (post_exam_evaluation_sync)
    2. 运维侧批量补传历史 exam (batch_post_evaluations_sync), 用于:
        - 上报功能合入之前已 completed 的存量数据
        - worker 异常 / 网络抖动导致单条上报失败后的人工重报

设计要点:
    - 全部使用同步 httpx + sync Session, 与 Celery worker 进程模型一致;
      在 FastAPI 异步路由里通过 run_in_threadpool 调用即可.
    - 单条失败仅记日志不抛异常 (与原 _post_remote_evaluation 一致),
      批量场景统一返回 BatchResult 摘要, 便于运维 API 回显失败明细.
    - payload 构造从 ORM 对象直接取值, 与原 Celery 任务逻辑保持一一对应,
      避免远端字段映射在两条路径上漂移.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.cpr_metrics import CprMetrics
from backend.app.models.exam import Exam


@dataclass
class ReportOutcome:
    """单条上报结果 - 给批量场景做汇总和审计"""

    exam_id: int
    ok: bool
    status_code: int | None = None
    response_body: str = ""
    error: str = ""


@dataclass
class BatchResult:
    """批量上报汇总 - 直接序列化给前端/运维"""

    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    outcomes: list[ReportOutcome] = field(default_factory=list)


# 远端 evaluation-add 接口要求的考核日期格式: "YYYY-MM-DD HH:II:SS" (空格分隔, 无微秒).
# 用 isoformat() 会输出带 'T' 和微秒, 远端会回 PARAM_ERROR "考核日期格式错误".
_REMOTE_EVAL_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def build_evaluation_payload(
    exam_id: int,
    device_code: str | None,
    total_score: float | None,
    created_at: datetime | None,
    session_duration_sec: float | None,
) -> dict:
    """构造远端 evaluation-add 接口 payload.

    字段含义与原 _post_remote_evaluation 完全一致 (远端文档对齐):
        - terminal_id: 设备软件 ID, 直接透传 device_code
        - users_id:    无用户体系, 留空
        - score:       得分, 四舍五入为整数
        - use_at:      用时(秒), 取 cpr_metrics.session_duration_sec, 无指标记 0
        - video_url:   本服务原始视频流式播放接口完整 URL (远端 H5 内嵌)
        - evaluation_at: 考核时间, 格式 "YYYY-MM-DD HH:II:SS" (远端强校验)
        - pdf_url:     本服务 PDF 内联查看接口完整 URL (远端浏览器预览)
    """
    base = settings.public_base_url.rstrip("/")
    return {
        "terminal_id": device_code or "",
        "users_id": "",
        "score": int(round(total_score or 0.0)),
        "use_at": int(session_duration_sec) if session_duration_sec else 0,
        "video_url": f"{base}/exam/{exam_id}/video/play",
        "evaluation_at": (
            created_at.strftime(_REMOTE_EVAL_DATETIME_FMT) if created_at else ""
        ),
        "pdf_url": f"{base}/exam/{exam_id}/report/pdf/view",
    }


def _post_payload(exam_id: int, payload: dict) -> ReportOutcome:
    """同步 POST 一次, 网络异常 / 超时不抛, 统一封装为 ReportOutcome.

    入口/出口均打印中文日志, 便于在容器日志里 grep [远端上报] 追踪整条链路.
    """
    url = settings.remote_eval_report_url
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRF-TOKEN": "",
        # 平台分配的 appid/appsecret 拼装而成: base64(APPID:md5(APPSECRET))
        "Authorization": settings.remote_eval_authorization,
    }

    logger.info(
        f"[远端上报] 准备发送: exam_id={exam_id}, url={url}, payload={payload}"
    )

    try:
        with httpx.Client(timeout=settings.remote_eval_report_timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
    except Exception as exc:
        # 网络异常 / 超时 / DNS 失败等 - 完整堆栈输出, 不再向外抛
        logger.exception(
            f"[远端上报] 调用失败 (本地流程继续): exam_id={exam_id}, err={exc}"
        )
        return ReportOutcome(exam_id=exam_id, ok=False, error=str(exc))

    body_preview = resp.text[:500] if resp.text else ""
    if 200 <= resp.status_code < 300:
        logger.info(
            f"[远端上报] 成功: exam_id={exam_id}, status={resp.status_code}, "
            f"body={body_preview}"
        )
        return ReportOutcome(
            exam_id=exam_id,
            ok=True,
            status_code=resp.status_code,
            response_body=body_preview,
        )

    # 4xx/5xx - 远端拒绝, 输出响应体便于排查
    logger.warning(
        f"[远端上报] 远端返回非 2xx: exam_id={exam_id}, "
        f"status={resp.status_code}, body={body_preview}"
    )
    return ReportOutcome(
        exam_id=exam_id,
        ok=False,
        status_code=resp.status_code,
        response_body=body_preview,
        error=f"http {resp.status_code}",
    )


def post_exam_evaluation_sync(
    exam_id: int,
    device_code: str | None,
    total_score: float | None,
    created_at: datetime | None,
    session_duration_sec: float | None,
) -> ReportOutcome:
    """单条上报 - Celery worker 评分完成后调用 (字段已提前从 ORM 取出)"""
    payload = build_evaluation_payload(
        exam_id=exam_id,
        device_code=device_code,
        total_score=total_score,
        created_at=created_at,
        session_duration_sec=session_duration_sec,
    )
    return _post_payload(exam_id, payload)


def post_evaluation_for_exam_sync(db: Session, exam_id: int) -> ReportOutcome:
    """按 exam_id 查库后上报 - 给单条手动重报 / 批量循环复用.

    跳过条件 (返回 ok=False, error 标注原因, 不算成功也不算失败的网络问题):
        - exam 不存在
        - exam.status != 'completed' (未评分完成的记录不应上报)
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        logger.warning(f"[远端上报] 跳过: exam_id={exam_id} 不存在")
        return ReportOutcome(exam_id=exam_id, ok=False, error="exam_not_found")

    if exam.status != "completed":
        logger.info(
            f"[远端上报] 跳过: exam_id={exam_id} 状态={exam.status} (非 completed)"
        )
        return ReportOutcome(
            exam_id=exam_id, ok=False, error=f"status={exam.status}"
        )

    metrics = (
        db.query(CprMetrics).filter(CprMetrics.exam_id == exam_id).first()
    )
    session_duration = metrics.session_duration_sec if metrics else None

    return post_exam_evaluation_sync(
        exam_id=exam.id,
        device_code=exam.device_code,
        total_score=exam.total_score,
        created_at=exam.created_at,
        session_duration_sec=session_duration,
    )


def batch_post_evaluations_sync(
    db: Session,
    exam_ids: Iterable[int] | None = None,
    only_completed: bool = True,
    limit: int | None = None,
) -> BatchResult:
    """批量补传 exams 表数据到远端考核中心.

    入参:
        - exam_ids: 指定 exam_id 列表; 为 None 时按 only_completed 全表扫描
        - only_completed: 全表扫描时, 是否仅取 status='completed' 的记录
        - limit: 限制一次最多上报多少条 (None 表示不限, 全表扫描场景建议设上限)

    返回 BatchResult, 包含每条的成功/失败明细.
    """
    if exam_ids is not None:
        target_ids = list(exam_ids)
    else:
        query = db.query(Exam.id)
        if only_completed:
            query = query.filter(Exam.status == "completed")
        query = query.order_by(Exam.created_at.asc())
        if limit is not None:
            query = query.limit(limit)
        target_ids = [row[0] for row in query.all()]

    result = BatchResult(total=len(target_ids))
    logger.info(
        f"[远端上报-批量] 开始: 目标条数={result.total}, "
        f"only_completed={only_completed}, limit={limit}"
    )

    for exam_id in target_ids:
        outcome = post_evaluation_for_exam_sync(db, exam_id)
        result.outcomes.append(outcome)
        if outcome.ok:
            result.success += 1
        elif outcome.error in ("exam_not_found",) or outcome.error.startswith(
            "status="
        ):
            # 跳过类: 数据不满足上报条件, 不当作真实失败
            result.skipped += 1
        else:
            result.failed += 1

    logger.info(
        f"[远端上报-批量] 结束: total={result.total}, success={result.success}, "
        f"failed={result.failed}, skipped={result.skipped}"
    )
    return result
