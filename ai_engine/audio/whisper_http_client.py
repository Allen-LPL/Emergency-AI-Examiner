# pyright: reportMissingImports=false
"""Whisper HTTP ASR client."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

__all__ = ["WhisperHTTPClient"]


class WhisperHTTPClient:
    def __init__(self, url: str = "http://172.28.0.1:9000/asr", timeout: int = 120):
        self.url = url
        self.timeout = timeout

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        logger.info(f"[WhisperHTTPClient] Transcribing {audio_path}")
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with open(audio_path, "rb") as audio_file:
                    response = client.post(
                        self.url,
                        params={"language": "zh"},
                        files={"audio_file": audio_file},
                    )
            response.raise_for_status()
            data = response.json()
            return {
                "text": str(data.get("text", "")),
                "language": str(data.get("language", "zh")),
                "segments": data.get("segments", []),
            }
        except (OSError, httpx.HTTPError, ValueError, AttributeError, TypeError) as exc:
            logger.error(f"[WhisperHTTPClient] Transcription failed: {exc}")
            return {"text": "", "segments": []}
