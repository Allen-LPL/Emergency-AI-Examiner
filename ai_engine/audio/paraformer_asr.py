# pyright: reportMissingImports=false
"""ASR: FunASR Paraformer-large 中文语音识别 (替代 SenseVoiceSmall).

模型选型理由:
    - paraformer-large 中文 CER 在 AISHELL-1 / WenetSpeech 上明显优于 SenseVoiceSmall
    - 支持 hotword (急救场景下"除颤""肾上腺素"等专业词必须强化)
    - 通过 ModelScope 可在国内拉取, 无需访问 HuggingFace

工作流:
    1. 初始化时一次性加载主模型 + 标点模型, 避免每段重复 load
    2. 对每个 SpeechSegment, 用 soundfile 切出对应音频片段写入临时 wav
    3. 调用 model.generate(input=chunk_wav, hotword=...)
    4. 解析 result, 取 text + 置信度 (Paraformer 不显式给 confidence, 这里留 None)
    5. 单段失败不影响其它段
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

from ai_engine.audio.types import SpeechSegment

try:
    import soundfile as sf
except ImportError:  # pragma: no cover
    sf = None  # type: ignore

try:
    from funasr import AutoModel  # type: ignore
except ImportError:  # pragma: no cover
    AutoModel = None  # type: ignore
    logger.warning("funasr 未安装, ParaformerASR 不可用")


DEFAULT_MODEL = (
    "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
)
DEFAULT_PUNC_MODEL = "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"


class ParaformerASR:
    """FunASR Paraformer 封装, 仅在初始化时加载一次模型.

    Args:
        model_name: 主 ASR 模型 ID (ModelScope), 默认 paraformer-large.
        punc_model: 标点模型 ID, None 表示禁用标点.
        device: "cuda:0" / "cpu", 自动降级.
        hub: 模型来源, "ms" = ModelScope, "hf" = HuggingFace, 默认 ms.
        disable_update: 关闭 funasr 启动时的版本检查, 减少日志噪音.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        punc_model: Optional[str] = DEFAULT_PUNC_MODEL,
        device: str = "cuda:0",
        hub: str = "ms",
        disable_update: bool = True,
    ) -> None:
        self.model_name = model_name
        self.punc_model = punc_model
        self.hub = hub
        self.disable_update = disable_update
        self.device = self._resolve_device(device)
        self.model = None

        if AutoModel is None:
            logger.error(
                "funasr.AutoModel 不可用, 无法初始化 ParaformerASR"
            )
            return

        self._load_model()

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #
    def _resolve_device(self, device: str) -> str:
        if "cuda" not in device:
            return device
        try:
            import torch

            if torch.cuda.is_available():
                return device
            logger.warning(
                f"[ParaformerASR] 请求 device={device} 但 CUDA 不可用, 降级 CPU"
            )
            return "cpu"
        except ImportError:
            return "cpu"

    def _load_model(self) -> None:
        try:
            logger.info(
                f"[ParaformerASR] 加载模型: model={self.model_name}, "
                f"punc={self.punc_model}, device={self.device}, hub={self.hub}"
            )
            kwargs = {
                "model": self.model_name,
                "device": self.device,
                "hub": self.hub,
                "disable_update": self.disable_update,
            }
            if self.punc_model:
                kwargs["punc_model"] = self.punc_model

            self.model = AutoModel(**kwargs)
            logger.info("[ParaformerASR] 模型加载完成")
        except Exception as exc:
            logger.exception(f"[ParaformerASR] 模型加载失败: {exc}")
            self.model = None

    # ------------------------------------------------------------------ #
    # 转写
    # ------------------------------------------------------------------ #
    def transcribe_segments(
        self,
        audio_path: str,
        segments: list[SpeechSegment],
        hotword: str = "",
        sample_rate: int = 16000,
    ) -> list[SpeechSegment]:
        """对每个 SpeechSegment 调用 Paraformer 转写, 把 raw_text 写回段内.

        失败的段保留 raw_text=None, 不会中断整个流程.
        """
        if not segments:
            return []

        if self.model is None:
            logger.warning("[ParaformerASR] 模型不可用, 跳过 ASR")
            return segments

        if sf is None:
            logger.error(
                "[ParaformerASR] soundfile 未安装, 无法切割音频片段"
            )
            return segments

        try:
            waveform, sr = sf.read(audio_path, dtype="float32")
        except Exception as exc:
            logger.exception(f"[ParaformerASR] 读取音频失败: {exc}")
            return segments

        if sr != sample_rate:
            logger.warning(
                f"[ParaformerASR] 采样率不匹配 (file={sr} vs target={sample_rate}), "
                f"建议先用 AudioPreprocessor 归一化"
            )

        ok_count = 0
        fail_count = 0
        with tempfile.TemporaryDirectory(prefix="paraformer_chunks_") as tmpdir:
            for idx, seg in enumerate(segments):
                chunk_path = self._dump_chunk(
                    waveform, sr, seg.start, seg.end, tmpdir, idx
                )
                if chunk_path is None:
                    fail_count += 1
                    continue
                try:
                    raw = self._asr_one(chunk_path, hotword=hotword)
                    seg.raw_text = raw
                    ok_count += 1
                except Exception as exc:
                    logger.warning(
                        f"[ParaformerASR] 第 {idx} 段转写失败 "
                        f"({seg.start:.2f}~{seg.end:.2f}, speaker={seg.speaker}): {exc}"
                    )
                    fail_count += 1

        logger.info(
            f"[ParaformerASR] 转写完成: 成功={ok_count}, 失败={fail_count}, "
            f"总段数={len(segments)}"
        )
        return segments

    # ------------------------------------------------------------------ #
    # 私有: 切割音频 + 单段 ASR
    # ------------------------------------------------------------------ #
    def _dump_chunk(
        self,
        waveform,
        sr: int,
        start: float,
        end: float,
        tmpdir: str,
        idx: int,
    ) -> Optional[str]:
        """把 waveform[start:end] 切出来写到临时 wav, 返回路径."""
        try:
            i_start = max(0, int(start * sr))
            i_end = min(len(waveform), int(end * sr))
            if i_end <= i_start:
                return None
            chunk = waveform[i_start:i_end]
            chunk_path = os.path.join(tmpdir, f"chunk_{idx:05d}.wav")
            sf.write(chunk_path, chunk, sr)
            return chunk_path
        except Exception as exc:
            logger.warning(f"[ParaformerASR] 切片失败 idx={idx}: {exc}")
            return None

    def _asr_one(self, chunk_path: str, hotword: str = "") -> str:
        """对单段 wav 调用 Paraformer, 返回拼好的文本."""
        kwargs: dict = {
            "input": chunk_path,
            "batch_size_s": 60,
        }
        if hotword:
            kwargs["hotword"] = hotword

        result = self.model.generate(**kwargs)  # type: ignore[union-attr]
        # FunASR 输出形如 [{"key": "...", "text": "...", "timestamp": [...]}]
        if not result:
            return ""
        if isinstance(result, list):
            text_parts = []
            for item in result:
                if isinstance(item, dict):
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            return "".join(text_parts).strip()
        if isinstance(result, dict):
            return str(result.get("text", "")).strip()
        return str(result).strip()


__all__ = ["ParaformerASR", "DEFAULT_MODEL", "DEFAULT_PUNC_MODEL"]
