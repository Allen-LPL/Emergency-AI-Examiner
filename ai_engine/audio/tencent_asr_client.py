# pyright: reportMissingImports=false
"""腾讯云录音文件识别 ASR 客户端 (异步任务接口).

为什么用录音文件识别 (CreateRecTask) 而非流式:
    考核录像通常 1-10 分钟, 已经落盘成完整 wav, 批量异步任务最贴合现有
    AudioPipeline 的"收完整文件 → 三路并行 → 合并"流水, 不需要重新切片推流.

参数与 Android 端 TXVoiceRecognizeManager.java 对齐:
    EngineModelType=16k_zh      引擎模型 (16k 中文通用)
    ChannelNum=1                单声道
    ResTextFormat=2             带词级时间戳的 JSON 结果
    SourceType=1                语音数据 (base64 编码)
    FilterDirty=0               不过滤脏话
    FilterModal=0               不过滤语气词
    FilterPunc=0                不过滤句末标点
    ConvertNumMode=1            智能转换阿拉伯数字

返回结构与 FunASRWebSocketClient 一致, 便于 ASRMerger 复用:
    {"text": str, "segments": [{"start": float, "end": float, "text": str}]}

凭证未配齐时静默返回空结果, 不抛异常, 不影响主链路.
"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any

from loguru import logger

try:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.asr.v20190614 import asr_client, models
except ImportError:
    credential = None
    ClientProfile = None  # type: ignore[assignment,misc]
    HttpProfile = None  # type: ignore[assignment,misc]
    asr_client = None  # type: ignore[assignment,misc]
    models = None  # type: ignore[assignment,misc]


# 腾讯云录音文件识别 Data 字段最大 5MB (base64 编码后),
# 对应原始 PCM 约 3.75MB. 16k mono 16bit PCM 约 32KB/s, 约能装 2min 音频.
# wav 容器带头部但有压缩感, 16k mono PCM-16 wav 约 32KB/s, 实际能装 ~2min.
# 超过此阈值需要走 COS URL 模式, 目前先抛错明示, 后续按需扩展.
_MAX_DATA_BYTES = 5 * 1024 * 1024  # 5MB 编码前安全阈值

# 腾讯返回的 Result 字段格式: "[0:0.480,0:3.220]  你好,介绍急救包\n[0:3.220,0:6.480]  ..."
# 时间戳格式: [分:秒.毫秒,分:秒.毫秒]
_SEGMENT_RE = re.compile(
    r"\[(\d+):(\d+)\.(\d+),(\d+):(\d+)\.(\d+)\]\s*(.+)"
)


class TencentASRClient:
    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        app_id: int,
        engine_type: str = "16k_zh",
        timeout: int = 600,
        poll_interval: float = 3.0,
    ):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.app_id = app_id
        self.engine_type = engine_type
        self.timeout = timeout
        self.poll_interval = poll_interval

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        # 凭证缺失静默跳过, 不影响主链路
        if not self.secret_id or not self.secret_key or self.app_id <= 0:
            logger.warning(
                "[TencentASRClient] 凭证未配置 (secret_id/secret_key/app_id), "
                "跳过腾讯 ASR"
            )
            return self._empty_result()

        if asr_client is None or credential is None:
            logger.error(
                "[TencentASRClient] tencentcloud-sdk-python 未安装, "
                "请 pip install tencentcloud-sdk-python"
            )
            return self._empty_result()

        if not Path(audio_path).exists():
            logger.error(f"[TencentASRClient] 文件不存在: {audio_path}")
            return self._empty_result()

        t0 = time.monotonic()
        logger.info(
            f"[TencentASRClient] 开始转写: file={audio_path}, "
            f"engine={self.engine_type}, timeout={self.timeout}s"
        )

        try:
            with open(audio_path, "rb") as f:
                raw_bytes = f.read()
            data_len = len(raw_bytes)
            if data_len > _MAX_DATA_BYTES:
                logger.error(
                    f"[TencentASRClient] 音频过大 ({data_len/1024/1024:.1f}MB), "
                    f"超过 Data 模式上限 {_MAX_DATA_BYTES/1024/1024:.0f}MB; "
                    f"长音频需走 COS URL 模式 (待扩展)"
                )
                return self._empty_result()

            data_b64 = base64.b64encode(raw_bytes).decode("utf-8")

            client = self._build_client()
            task_id = self._create_task(client, data_b64, data_len)
            logger.info(
                f"[TencentASRClient] CreateRecTask 提交成功: task_id={task_id}"
            )

            result_text = self._poll_task(client, task_id, t0)
            if not result_text:
                return self._empty_result()

            segments = self._parse_result_text(result_text)
            joined_text = "".join(s["text"] for s in segments) if segments else ""
            # Result 里把时间戳行去掉就是干净文本
            full_text = joined_text or re.sub(
                r"\[\d+:\d+\.\d+,\d+:\d+\.\d+\]\s*", "", result_text
            ).strip()

            elapsed = time.monotonic() - t0
            logger.info(
                f"[TencentASRClient] 转写成功: {len(full_text)}字, "
                f"耗时={elapsed:.1f}s, segments={len(segments)}"
            )
            # 完整文本落日志便于复盘 ASR 质量 (用户明确要求)
            logger.info(f"[TencentASRClient] 转写文本: {full_text}")

            return {"text": full_text, "segments": segments}

        except _TencentTaskFailed as exc:
            logger.error(
                f"[TencentASRClient] 任务失败: task_id={exc.task_id}, "
                f"error_msg={exc.error_msg}"
            )
        except _TencentPollTimeout as exc:
            logger.error(
                f"[TencentASRClient] 轮询超时 ({self.timeout}s): "
                f"task_id={exc.task_id}, 已耗时={exc.elapsed:.1f}s"
            )
        except Exception as exc:
            # SDK 抛 TencentCloudSDKException 时也会带 RequestId, 在 str(exc) 里
            logger.exception(
                f"[TencentASRClient] 转写异常 ({type(exc).__name__}): {exc}"
            )

        return self._empty_result()

    def _build_client(self) -> Any:
        assert credential is not None
        assert ClientProfile is not None
        assert HttpProfile is not None
        assert asr_client is not None

        cred = credential.Credential(self.secret_id, self.secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = "asr.tencentcloudapi.com"
        # 单次 HTTP 调用超时 (秒); 总超时由 _poll_task 控制
        http_profile.reqTimeout = 60
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        # 区域对 ASR API 不敏感, 用 ap-beijing 即可
        return asr_client.AsrClient(cred, "ap-beijing", client_profile)

    def _create_task(self, client: Any, data_b64: str, data_len: int) -> int:
        assert models is not None
        req = models.CreateRecTaskRequest()
        params = {
            "EngineModelType": self.engine_type,
            "ChannelNum": 1,
            "ResTextFormat": 2,    # 带词级时间戳的 JSON 格式
            "SourceType": 1,       # 1 = 语音数据 (Data 字段 base64)
            "Data": data_b64,
            "DataLen": data_len,
            "FilterDirty": 0,
            "FilterModal": 0,
            "FilterPunc": 0,
            "ConvertNumMode": 1,
        }
        req.from_json_string(json.dumps(params))
        resp = client.CreateRecTask(req)
        # resp.Data.TaskId
        return int(resp.Data.TaskId)

    def _poll_task(self, client: Any, task_id: int, t_start: float) -> str:
        assert models is not None
        poll_count = 0
        while True:
            elapsed = time.monotonic() - t_start
            if elapsed > self.timeout:
                raise _TencentPollTimeout(task_id, elapsed)

            req = models.DescribeTaskStatusRequest()
            req.from_json_string(json.dumps({"TaskId": task_id}))
            resp = client.DescribeTaskStatus(req)
            data = resp.Data
            status_str = (getattr(data, "StatusStr", "") or "").lower()

            poll_count += 1
            # 每 3 次轮询打一次进度, 避免刷屏 (3*poll_interval ≈ 9s)
            if poll_count % 3 == 0:
                logger.info(
                    f"[TencentASRClient] 轮询 task={task_id} "
                    f"status={status_str} 已耗时={elapsed:.1f}s"
                )

            if status_str == "success":
                return getattr(data, "Result", "") or ""
            if status_str == "failed":
                err_msg = getattr(data, "ErrorMsg", "") or "unknown"
                raise _TencentTaskFailed(task_id, err_msg)

            # waiting / doing 继续轮询
            time.sleep(self.poll_interval)

    @staticmethod
    def _parse_result_text(result_text: str) -> list[dict[str, Any]]:
        """解析 [mm:ss.fff,mm:ss.fff] 文本格式为 segments 列表。"""
        if not result_text:
            return []
        segments: list[dict[str, Any]] = []
        for raw_line in result_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = _SEGMENT_RE.match(line)
            if not m:
                continue
            s_min, s_sec, s_ms, e_min, e_sec, e_ms, text = m.groups()
            start = int(s_min) * 60 + int(s_sec) + int(s_ms) / 1000.0
            end = int(e_min) * 60 + int(e_sec) + int(e_ms) / 1000.0
            text_clean = text.strip()
            if not text_clean:
                continue
            segments.append({
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text_clean,
            })
        return segments

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {"text": "", "segments": []}


class _TencentTaskFailed(Exception):
    def __init__(self, task_id: int, error_msg: str):
        super().__init__(f"task {task_id} failed: {error_msg}")
        self.task_id = task_id
        self.error_msg = error_msg


class _TencentPollTimeout(Exception):
    def __init__(self, task_id: int, elapsed: float):
        super().__init__(f"task {task_id} poll timeout after {elapsed:.1f}s")
        self.task_id = task_id
        self.elapsed = elapsed


__all__ = ["TencentASRClient"]
