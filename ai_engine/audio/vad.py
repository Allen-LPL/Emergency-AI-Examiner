# pyright: reportMissingImports=false
"""VAD (Voice Activity Detection) - 基于 FunASR fsmn-vad.

独立于说话人分离，提供可靠的人声片段检测。
即使 pyannote diarization 失败，VAD 仍然能把长音频切成短语音片段，
避免整段音频进入 ASR 产生幻听。

输出: list[VadSegment]，每个 segment 为 (start, end) 秒级时间戳。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

try:
    from funasr import AutoModel  # type: ignore
except ImportError:  # pragma: no cover
    AutoModel = None  # type: ignore

DEFAULT_VAD_MODEL = "fsmn-vad"
MAX_SINGLE_SEGMENT_TIME = 30000  # ms
MIN_SEGMENT_DURATION = 0.5  # seconds


@dataclass
class VadSegment:
    start: float
    end: float


class VoiceActivityDetector:
    """FunASR fsmn-vad 封装，检测音频中的有效人声片段。

    Args:
        model_name: FunASR VAD 模型 ID，默认 fsmn-vad (ModelScope 短名)。
        max_single_segment_time: 单段最大时长 (毫秒)，超过会被 VAD 切分。
        min_segment_duration: 过滤阈值 (秒)，短于此的片段丢弃。
    """

    def __init__(
        self,
        model_name: str = DEFAULT_VAD_MODEL,
        max_single_segment_time: int = MAX_SINGLE_SEGMENT_TIME,
        min_segment_duration: float = MIN_SEGMENT_DURATION,
    ) -> None:
        self.model_name = model_name
        self.max_single_segment_time = max_single_segment_time
        self.min_segment_duration = min_segment_duration
        self.model = None

        if AutoModel is None:
            logger.error("[VAD] funasr.AutoModel 不可用, VAD 将不可用")
            return

        try:
            logger.info(f"[VAD] 加载模型: {model_name}")
            self.model = AutoModel(
                model=model_name,
                hub="ms",
                disable_update=True,
            )
            logger.info("[VAD] 模型加载完成")
        except Exception as exc:
            logger.exception(f"[VAD] 模型加载失败: {exc}")
            self.model = None

    @property
    def enabled(self) -> bool:
        return self.model is not None

    def detect(self, audio_path: str) -> list[VadSegment]:
        """检测音频中的有效人声片段。

        返回按 start 排序的 VadSegment 列表。
        模型不可用或检测失败时返回空列表。
        """
        if self.model is None:
            logger.warning("[VAD] 模型不可用, 返回空 VAD segments")
            return []

        try:
            result = self.model.generate(
                input=audio_path,
                max_single_segment_time=self.max_single_segment_time,
            )
        except Exception as exc:
            logger.exception(f"[VAD] 检测失败: {exc}")
            return []

        segments = self._parse_result(result)
        segments.sort(key=lambda s: s.start)

        total_speech = sum(s.end - s.start for s in segments)
        logger.info(
            f"[VAD] 检测完成: {len(segments)}段, "
            f"有效语音时长={total_speech:.1f}s"
        )
        return segments

    def _parse_result(self, result: object) -> list[VadSegment]:
        """解析 FunASR fsmn-vad 输出。

        FunASR 输出格式:
            [{"key": "...", "value": [[start_ms, end_ms], ...]}]
        """
        segments: list[VadSegment] = []
        if not isinstance(result, list):
            return segments

        for item in result:
            if not isinstance(item, dict):
                continue
            intervals = item.get("value", [])
            if not isinstance(intervals, list):
                continue
            for interval in intervals:
                if not isinstance(interval, (list, tuple)) or len(interval) < 2:
                    continue
                try:
                    start_s = float(interval[0]) / 1000.0
                    end_s = float(interval[1]) / 1000.0
                except (TypeError, ValueError):
                    continue
                if (end_s - start_s) >= self.min_segment_duration:
                    segments.append(
                        VadSegment(start=round(start_s, 3), end=round(end_s, 3))
                    )

        return segments


__all__ = [
    "VoiceActivityDetector",
    "VadSegment",
    "DEFAULT_VAD_MODEL",
    "MAX_SINGLE_SEGMENT_TIME",
    "MIN_SEGMENT_DURATION",
]
