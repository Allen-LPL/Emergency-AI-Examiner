# pyright: reportMissingImports=false
"""Whisper HTTP ASR 客户端。

设计要点:
    1. 失败原因分桶 (超时 / HTTP 状态 / 网络 / 其他), 每一类都打印足够定位的现场信息;
    2. 成功后把完整转写文本落到 INFO 日志, 便于人工复盘 ASR 质量;
    3. 默认超时 600s, 适配 5+ 分钟的考核音频; 连接超时单独设 15s 避免被 hang 死.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

__all__ = ["WhisperHTTPClient"]


class WhisperHTTPClient:
    def __init__(self, url: str = "http://172.28.0.1:9000/asr", timeout: int = 600):
        self.url = url
        self.timeout = timeout

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        t0 = time.monotonic()
        logger.info(
            f"[WhisperHTTPClient] 开始转写: file={audio_path}, "
            f"url={self.url}, timeout={self.timeout}s"
        )
        try:
            # connect=15s 用于快速感知服务不可达; 总超时 self.timeout 覆盖长音频上传+推理
            with httpx.Client(
                timeout=httpx.Timeout(self.timeout, connect=15.0)
            ) as client:
                with open(audio_path, "rb") as audio_file:
                    response = client.post(
                        self.url,
                        # output=json: whisper-asr-webservice 默认返回纯文本,
                        # 显式要 JSON 才有 text/language/segments 字段
                        params={"language": "zh", "output": "json"},
                        files={"audio_file": audio_file},
                    )
            response.raise_for_status()
            text, language, segments = self._parse_response(response)
            elapsed = time.monotonic() - t0
            logger.info(
                f"[WhisperHTTPClient] 转写成功: {len(text)}字, "
                f"耗时={elapsed:.1f}s, language={language}, "
                f"segments={len(segments)}"
            )
            # 把完整转写文本落到日志, 便于人工复盘 ASR 质量 (用户明确要求)
            logger.info(f"[WhisperHTTPClient] 转写文本: {text}")
            return {"text": text, "language": language, "segments": segments}
        except httpx.TimeoutException as exc:
            elapsed = time.monotonic() - t0
            logger.error(
                f"[WhisperHTTPClient] 请求超时 ({self.timeout}s): "
                f"file={audio_path}, 耗时={elapsed:.1f}s, exc={exc}"
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response is not None else ""
            status = exc.response.status_code if exc.response is not None else -1
            logger.error(
                f"[WhisperHTTPClient] HTTP {status} 错误: "
                f"url={self.url}, body={body}"
            )
        except httpx.HTTPError as exc:
            logger.error(
                f"[WhisperHTTPClient] 网络/传输错误 "
                f"({type(exc).__name__}): {exc}"
            )
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            logger.exception(
                f"[WhisperHTTPClient] 转写异常 ({type(exc).__name__}): {exc}"
            )
        return {"text": "", "segments": []}

    @staticmethod
    def _parse_response(response: httpx.Response) -> tuple[str, str, list]:
        """兼容 JSON 与纯文本两种响应。

        whisper-asr-webservice 在 output=json 时返回 JSON, 但 Content-Type 不一定带 json
        (实测有的 fork 是 text/plain), 所以双重判断: header 含 json 或 body 看起来像 JSON
        ({ / [ 开头) 都先按 JSON 解析; JSON 解析失败再退回纯文本兜底.

        历史 bug: 早期版本只看 Content-Type, 结果 Whisper 服务返回 JSON 但 header 是
        text/plain, 整段 JSON 字符串被当成 text 存进去 (出现过 66292字、segments=0、
        转写文本首字符是 '{' 的现象).
        """
        body_text = (response.text or "").strip()
        ctype = response.headers.get("content-type", "").lower()
        looks_json = "json" in ctype or body_text.startswith(("{", "["))
        if looks_json:
            try:
                data = response.json()
            except ValueError:
                data = None
            if isinstance(data, dict):
                return (
                    str(data.get("text", "")),
                    str(data.get("language", "zh")),
                    data.get("segments", []) or [],
                )
        # 纯文本: 直接当 text, 没有 segments
        return body_text, "zh", []
