# pyright: reportMissingImports=false
"""FunASR WebSocket ASR client (offline mode)."""

from __future__ import annotations

import asyncio
import json
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
        timeout: int = 120,
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

        logger.info(
            f"[FunASRWebSocketClient] 开始转写: {audio_path}, "
            f"server={self.url}, hotwords={len(hotwords)}字符"
        )

        try:
            loop = self._get_or_create_loop()
            result = loop.run_until_complete(
                self._transcribe_async(audio_path, hotwords)
            )
            return result
        except Exception as exc:
            logger.error(f"[FunASRWebSocketClient] 转写失败: {exc}")
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
            open_timeout=30,
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
            except Exception:
                pass

        logger.info(
            f"[FunASRWebSocketClient] 转写完成: "
            f"{len(final_text)}字, {len(all_segments)}段"
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
