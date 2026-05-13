# pyright: reportMissingImports=false
"""说话人分离 (Speaker Diarization) - 基于 pyannote.audio 3.1.

API 变更说明:
    - pyannote 3.x 使用 token= 参数, 旧 use_auth_token= 已废弃
    - 必须接受 https://hf.co/pyannote/speaker-diarization-3.1 的 license
    - 模型由 huggingface_hub 下载, 容器需要能访问 HF (已通过 v2ray 代理)

容错策略:
    - 无 HF_TOKEN / 网络不可达 / pipeline 加载失败 → 不抛异常, 返回空段
      由上层 (AudioPipeline) 决定是否退化为单 speaker 模式
    - GPU 不可用自动降级 CPU
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
UNKNOWN_SPEAKER = "UNKNOWN_SPEAKER"  # pipeline 失败时使用的占位说话人


class SpeakerDiarizer:
    """pyannote 3.1 说话人分离封装.

    Args:
        hf_token: HuggingFace token. 优先级: 显式参数 > 环境变量 HF_TOKEN > AI_HF_TOKEN.
        device: "cuda" / "cuda:0" / "cpu". 不可用时自动降级 CPU.
        num_speakers: 期望说话人数量 (急救场景默认 3: 医生/护士/驾驶员).
        model_name: pyannote 模型 ID, 默认 speaker-diarization-3.1.
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

        # token 优先级: 入参 > HF_TOKEN > AI_HF_TOKEN (兼容 pydantic-settings 命名)
        token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("AI_HF_TOKEN")

        if PyannotePipeline is None:
            logger.warning("pyannote.audio 不可用, 跳过说话人分离")
            return

        if not token:
            logger.warning(
                "未提供 HuggingFace token (HF_TOKEN / AI_HF_TOKEN), "
                "无法加载 pyannote 模型, 跳过说话人分离"
            )
            return

        try:
            logger.info(f"[Diarizer] 加载 pyannote 模型: {model_name}")
            self.pipeline = PyannotePipeline.from_pretrained(model_name, token=token)

            # 设备分配: 优先尝试请求的 device, 失败回退 CPU
            self._device_str = self._move_to_device(device)
            logger.info(f"[Diarizer] 模型已就绪, device={self._device_str}")
        except Exception as exc:
            logger.warning(f"[Diarizer] 加载失败: {exc}; 将跳过说话人分离")
            self.pipeline = None

    def _move_to_device(self, device: str) -> str:
        """把 pipeline 移到目标设备, 失败自动降级 CPU."""
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
        """对音频做说话人分离, 返回按 start 排序的 DiarizationSegment 列表.

        若 pipeline 加载失败, 返回空列表 (上层会触发单 speaker 兜底).
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
        """读取 wav 为 pyannote 内存输入, 避免 pipeline 内部走 torchcodec 解码。"""
        if sf is None:
            logger.warning("[Diarizer] soundfile 不可用, 无法构建 waveform 输入")
            return None
        if torch is None:
            logger.warning("[Diarizer] torch 不可用, 无法构建 waveform 输入")
            return None

        try:
            waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
        except Exception as exc:
            logger.exception(f"[Diarizer] 读取 waveform 失败: {exc}")
            return None

        waveform_tensor = torch.as_tensor(waveform, dtype=torch.float32)
        if waveform_tensor.ndim != 2:
            logger.warning(
                f"[Diarizer] waveform 维度异常: ndim={waveform_tensor.ndim}"
            )
            return None

        # soundfile 输出为 (time, channels), pyannote 需要 (channels, time)
        waveform_tensor = waveform_tensor.transpose(0, 1).contiguous()
        return {"waveform": waveform_tensor, "sample_rate": int(sample_rate)}


__all__ = ["SpeakerDiarizer", "DEFAULT_DIARIZATION_MODEL", "UNKNOWN_SPEAKER"]
