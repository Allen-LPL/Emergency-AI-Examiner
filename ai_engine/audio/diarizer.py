# pyright: reportMissingImports=false
"""说话人分离 (Speaker Diarization) - 基于 pyannote.audio 3.1.

API 兼容说明:
    pyannote/speaker-diarization-3.1 官方示例使用 use_auth_token，
    但不同 pyannote.audio / huggingface_hub 版本可能存在
    token / use_auth_token 参数差异，因此代码采用兼容加载策略:
    优先 use_auth_token，若 TypeError 则 fallback 到 token。

容错策略:
    无 HF_TOKEN / 网络不可达 / pipeline 加载失败 → 不抛异常, 返回空段
    由上层 (AudioPipeline) 决定是否退化; GPU 不可用自动降级 CPU.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from loguru import logger

from ai_engine.audio.types import DiarizationSegment

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None  # type: ignore

try:
    import soundfile as sf
except ImportError:  # pragma: no cover
    sf = None  # type: ignore

try:
    from pyannote.audio import Pipeline as PyannotePipeline
except ImportError:  # pragma: no cover
    PyannotePipeline = None  # type: ignore
    logger.warning("pyannote.audio 未安装, SpeakerDiarizer 将不可用")


DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
UNKNOWN_SPEAKER = "UNKNOWN_SPEAKER"


def _get_pyannote_version() -> str:
    try:
        import pyannote.audio
        return getattr(pyannote.audio, "__version__", "unknown")
    except Exception:
        return "not installed"


class SpeakerDiarizer:
    """pyannote 3.1 说话人分离封装。

    token 优先级: hf_token 入参 > HF_TOKEN > HUGGINGFACE_HUB_TOKEN > AI_HF_TOKEN.
    """

    def __init__(
        self,
        hf_token: Optional[str] = None,
        device: str = "cuda:0",
        num_speakers: int = 3,
        model_name: str = DEFAULT_DIARIZATION_MODEL,
    ) -> None:
        self.num_speakers = num_speakers
        self.model_name = model_name
        self.pipeline = None
        self._device_str: str = "cpu"

        token = (
            hf_token
            or os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGINGFACE_HUB_TOKEN")
            or os.environ.get("AI_HF_TOKEN")
        )

        if PyannotePipeline is None:
            logger.warning("pyannote.audio 不可用, 跳过说话人分离")
            return

        if not token:
            logger.warning(
                "未提供 HuggingFace token "
                "(HF_TOKEN / HUGGINGFACE_HUB_TOKEN / AI_HF_TOKEN), "
                "无法加载 pyannote 模型, 跳过说话人分离"
            )
            return

        try:
            logger.info(f"[Diarizer] 加载 pyannote 模型: {model_name}")
            self.pipeline = self._load_pyannote_pipeline(model_name, token)
            self._device_str = self._move_to_device(device)
            logger.info(f"[Diarizer] 模型已就绪, device={self._device_str}")
        except Exception as exc:
            logger.warning(
                f"[Diarizer] 加载失败: {type(exc).__name__}: {exc}\n"
                "请检查:\n"
                "  - HF_TOKEN / HUGGINGFACE_HUB_TOKEN / AI_HF_TOKEN 是否正确\n"
                "  - 是否已接受 pyannote/segmentation-3.0 访问条件\n"
                "  - 是否已接受 pyannote/speaker-diarization-3.1 访问条件\n"
                "  - 容器是否能访问 huggingface\n"
                f"  - pyannote.audio 版本: {_get_pyannote_version()}"
            )
            self.pipeline = None

    @staticmethod
    def _load_pyannote_pipeline(model_name: str, token: str) -> Any:
        """兼容加载: 优先 use_auth_token, fallback token."""
        try:
            return PyannotePipeline.from_pretrained(
                model_name, use_auth_token=token
            )
        except TypeError as exc:
            if "use_auth_token" in str(exc):
                logger.debug(
                    "[Diarizer] use_auth_token 不被当前版本支持, "
                    "fallback 到 token= 参数"
                )
                return PyannotePipeline.from_pretrained(
                    model_name, token=token
                )
            raise

    def _move_to_device(self, device: str) -> str:
        if torch is None or self.pipeline is None:
            return "cpu"
        if "cuda" in device and not torch.cuda.is_available():
            logger.warning(
                f"[Diarizer] 请求 device={device} 但 CUDA 不可用, 降级 CPU"
            )
            device = "cpu"
        try:
            self.pipeline.to(torch.device(device))
            return device
        except Exception as exc:
            logger.warning(f"[Diarizer] 移动到 {device} 失败 ({exc}), 降级 CPU")
            try:
                self.pipeline.to(torch.device("cpu"))
            except Exception:
                pass
            return "cpu"

    def diarize(
        self,
        audio_path: str,
        num_speakers: Optional[int] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[DiarizationSegment]:
        """对音频做说话人分离, 返回按 start 排序的 DiarizationSegment 列表。

        pipeline 不可用时返回空列表 (上层用 VAD segments 兜底).
        """
        if self.pipeline is None:
            logger.info("[Diarizer] pipeline 不可用, 返回空 diarization")
            return []

        kwargs: dict = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
        elif self.num_speakers:
            kwargs["num_speakers"] = self.num_speakers
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

        audio_input = self._load_waveform_input(audio_path)
        if audio_input is None:
            return []

        try:
            logger.info(
                f"[Diarizer] 开始分离: audio={audio_path}, kwargs={kwargs}"
            )
            diarization = self.pipeline(audio_input, **kwargs)
        except Exception as exc:
            logger.exception(f"[Diarizer] 分离失败: {exc}")
            return []

        segments: list[DiarizationSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                DiarizationSegment(
                    start=round(float(turn.start), 3),
                    end=round(float(turn.end), 3),
                    speaker=str(speaker),
                )
            )

        segments.sort(key=lambda s: s.start)
        speakers = sorted({s.speaker for s in segments})
        total_dur = sum(s.end - s.start for s in segments)
        logger.info(
            f"[Diarizer] 完成: {len(segments)}段, "
            f"speakers={speakers}, 总时长={total_dur:.1f}s"
        )
        return segments

    @staticmethod
    def _load_waveform_input(audio_path: str) -> dict[str, Any] | None:
        """读取 wav 为 pyannote 内存输入 {"waveform": (C, T), "sample_rate": int}."""
        if sf is None:
            logger.warning("[Diarizer] soundfile 不可用, 无法构建 waveform 输入")
            return None
        if torch is None:
            logger.warning("[Diarizer] torch 不可用, 无法构建 waveform 输入")
            return None

        try:
            waveform, sample_rate = sf.read(
                audio_path, dtype="float32", always_2d=True
            )
        except Exception as exc:
            logger.exception(f"[Diarizer] 读取 waveform 失败: {exc}")
            return None

        # shape: (time, channels)
        waveform_tensor = torch.as_tensor(waveform, dtype=torch.float32)
        if waveform_tensor.ndim != 2:
            logger.warning(
                f"[Diarizer] waveform 维度异常: ndim={waveform_tensor.ndim}"
            )
            return None

        if waveform_tensor.shape[1] > 1:
            logger.info(
                f"[Diarizer] 多声道 ({waveform_tensor.shape[1]}ch), "
                "自动合并为 mono"
            )
            waveform_tensor = waveform_tensor.mean(dim=1, keepdim=True)

        if sample_rate != 16000:
            logger.warning(
                f"[Diarizer] sample_rate={sample_rate}, 预期 16000Hz. "
                "上游预处理必须输出 16kHz mono wav"
            )

        # soundfile (time, channels) → pyannote (channels, time)
        waveform_tensor = waveform_tensor.transpose(0, 1).contiguous()
        return {"waveform": waveform_tensor, "sample_rate": int(sample_rate)}


__all__ = ["SpeakerDiarizer", "DEFAULT_DIARIZATION_MODEL", "UNKNOWN_SPEAKER"]
