# pyright: reportMissingImports=false
"""FunASR WebSocket ASR 客户端 (offline 模式).

设计要点:
    1. 失败原因分桶 (连接被拒 / 连接超时 / 协议异常 / 其他), 每一类都打印
       足够定位的现场信息, 避免历史上 `except Exception` 静默丢错;
    2. 成功后把完整转写文本落到 INFO 日志, 便于人工复盘 ASR 质量;
    3. 默认超时 600s, 适配 5+ 分钟考核音频; 连接超时 60s.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import websockets
    from websockets.legacy.client import connect as ws_connect
except ImportError:
    websockets = None
    ws_connect = None  # type: ignore[assignment,misc]

CHUNK_BYTES = 9600  # 0.3s at 16kHz 16bit mono


class FunASRWebSocketClient:
    def __init__(
        self,
        url: str = "ws://172.17.0.1:10095",
        timeout: int = 600,
    ):
        self.url = url
        self.timeout = timeout

    def transcribe(self, audio_path: str, hotwords: str = "") -> dict[str, Any]:
        if websockets is None:
            logger.error("[FunASRWebSocketClient] websockets 库未安装")
            return self._empty_result()
        if sf is None:
            logger.error("[FunASRWebSocketClient] soundfile 库未安装")
            return self._empty_result()
        if not Path(audio_path).exists():
            logger.error(f"[FunASRWebSocketClient] 文件不存在: {audio_path}")
            return self._empty_result()

        t0 = time.monotonic()
        logger.info(
            f"[FunASRWebSocketClient] 开始转写: file={audio_path}, "
            f"server={self.url}, timeout={self.timeout}s, "
            f"hotwords={len(hotwords)}字符"
        )

        try:
            loop = self._get_or_create_loop()
            result = loop.run_until_complete(
                self._transcribe_async(audio_path, hotwords)
            )
            elapsed = time.monotonic() - t0
            logger.info(
                f"[FunASRWebSocketClient] 转写完成: "
                f"{len(result.get('text', ''))}字, "
                f"{len(result.get('segments', []))}段, 耗时={elapsed:.1f}s"
            )
            # 完整文本落日志便于复盘 ASR 质量 (用户明确要求)
            logger.info(
                f"[FunASRWebSocketClient] 转写文本: {result.get('text', '')}"
            )
            return result
        except ConnectionRefusedError as exc:
            logger.error(
                f"[FunASRWebSocketClient] 连接被拒: server={self.url}, "
                f"请检查 FunASR 服务是否启动. exc={exc}"
            )
        except asyncio.TimeoutError as exc:
            elapsed = time.monotonic() - t0
            logger.error(
                f"[FunASRWebSocketClient] 连接/转写超时 ({self.timeout}s): "
                f"server={self.url}, 已耗时={elapsed:.1f}s, exc={exc}"
            )
        except OSError as exc:
            logger.error(
                f"[FunASRWebSocketClient] 网络错误 ({type(exc).__name__}): "
                f"server={self.url}, exc={exc}"
            )
        except Exception as exc:
            # websockets.exceptions.* 各类协议异常都走这里
            logger.exception(
                f"[FunASRWebSocketClient] 转写异常 ({type(exc).__name__}): {exc}"
            )
        return self._empty_result()

    async def _transcribe_async(
        self, audio_path: str, hotwords: str
    ) -> dict[str, Any]:
        assert sf is not None
        assert ws_connect is not None
        assert websockets is not None

        waveform, sr = sf.read(audio_path, dtype="int16")
        pcm_bytes = waveform.tobytes()

        async with ws_connect(
            self.url,
            max_size=None,
            open_timeout=60,
            close_timeout=10,
            ping_interval=None,
        ) as ws:
            config_msg = json.dumps(
                {
                    "mode": "offline",
                    "chunk_size": [5, 10, 5],
                    "chunk_interval": 10,
                    "audio_fs": sr,
                    "wav_name": Path(audio_path).stem,
                    "wav_format": "PCM",
                    "is_speaking": True,
                    "hotwords": hotwords,
                    "itn": False,
                },
                ensure_ascii=False,
            )
            await ws.send(config_msg)

            offset = 0
            while offset < len(pcm_bytes):
                chunk = pcm_bytes[offset : offset + CHUNK_BYTES]
                await ws.send(chunk)
                offset += CHUNK_BYTES

            await ws.send(json.dumps({"is_speaking": False}))

            final_text = ""
            all_segments: list[dict[str, Any]] = []

            try:
                async for msg in ws:
                    if isinstance(msg, str):
                        data = json.loads(msg)
                        text = data.get("text", "")
                        if text:
                            final_text = text
                        stamp_sents = data.get("stamp_sents", [])
                        if stamp_sents:
                            all_segments = self._parse_stamp_sents(stamp_sents)
            except Exception as exc:
                # 消息循环出错时, 已收到的结果不丢, 只 warn 一下供排查
                logger.warning(
                    f"[FunASRWebSocketClient] 消息循环异常 "
                    f"({type(exc).__name__}), 已收 {len(final_text)}字: {exc}"
                )

        return {"text": final_text, "segments": all_segments}

    def _parse_stamp_sents(
        self, stamp_sents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        for sent in stamp_sents:
            start_ms = sent.get("start", 0)
            end_ms = sent.get("end", 0)
            text_seg = (sent.get("text_seg", "") or "").replace(" ", "")
            if start_ms < 0 or end_ms < 0:
                continue
            if not text_seg:
                continue
            segments.append({
                "start": start_ms / 1000.0,
                "end": end_ms / 1000.0,
                "text": text_seg,
            })
        return segments

    @staticmethod
    def _get_or_create_loop() -> asyncio.AbstractEventLoop:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {"text": "", "segments": []}


__all__ = ["FunASRWebSocketClient"]
