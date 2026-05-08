# pyright: reportMissingImports=false
"""音频预处理: 把 video/wav 归一为 16kHz 单声道, 并应用降噪/响度归一/带通滤波。

为什么要预处理:
    1. pyannote 与 Paraformer 都对 16kHz mono 优化最好;
    2. 急救场景嘈杂, highpass/lowpass + afftdn 能显著提升 ASR 字符准确率;
    3. loudnorm 把音量拉到 EBU R128 标准, 避免远讲/近讲段差异过大.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger

# ffmpeg 滤镜链 (顺序敏感):
#   highpass=f=80   去除低频电源噪与桌面震动
#   lowpass=f=8000  限制高频, 16kHz 采样下 8k 是奈奎斯特上限的实用值
#   afftdn          基于 FFT 的自适应降噪
#   loudnorm        EBU R128 响度归一 (I=-16 LUFS, TP=-1.5 dB)
DEFAULT_FILTER_CHAIN = (
    "highpass=f=80,"
    "lowpass=f=8000,"
    "afftdn,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)


class AudioPreprocessor:
    """音频预处理器, 内部封装 ffmpeg 命令调用。

    Args:
        sample_rate: 输出采样率, 默认 16000 (pyannote/Paraformer 标准).
        filter_chain: ffmpeg 滤镜链, 默认 highpass+lowpass+afftdn+loudnorm.
        ffmpeg_bin: ffmpeg 可执行路径, 默认从 PATH 查找.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        filter_chain: str = DEFAULT_FILTER_CHAIN,
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self.sample_rate = sample_rate
        self.filter_chain = filter_chain
        self.ffmpeg_bin = ffmpeg_bin

    def process(self, input_path: str, output_path: str | None = None) -> str:
        """把 input 文件 (wav/mp4/mov 任意 ffmpeg 支持的容器) 处理为 16kHz mono wav.

        Returns:
            实际输出路径 (绝对路径).
        Raises:
            FileNotFoundError: 输入文件不存在
            RuntimeError: ffmpeg 执行失败
        """
        in_path = Path(input_path).resolve()
        if not in_path.exists():
            raise FileNotFoundError(f"音频/视频输入文件不存在: {in_path}")

        if output_path is None:
            # 默认在同目录生成 audio_preprocessed.wav, 避免覆盖原始 exam_audio.wav
            output_path = str(in_path.parent / "audio_preprocessed.wav")
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if shutil.which(self.ffmpeg_bin) is None:
            raise RuntimeError(
                f"未找到 ffmpeg 可执行文件 (检索: {self.ffmpeg_bin}), "
                "请确认容器内已安装 ffmpeg"
            )

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(in_path),
            "-ac",
            "1",  # 单声道
            "-ar",
            str(self.sample_rate),  # 采样率
            "-acodec",
            "pcm_s16le",
            "-af",
            self.filter_chain,
            str(out_path),
        ]

        logger.info(
            f"[音频预处理] 开始: input={in_path.name}, "
            f"output={out_path}, sr={self.sample_rate}Hz, "
            f"filter={self.filter_chain}"
        )
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"ffmpeg 预处理超时 (>600s): {in_path}")

        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg 预处理失败 (returncode={result.returncode}): "
                f"{result.stderr[:500]}"
            )

        size_mb = out_path.stat().st_size / (1024 * 1024) if out_path.exists() else 0
        logger.info(
            f"[音频预处理] 完成: {out_path} ({size_mb:.2f} MB)"
        )
        return str(out_path)


__all__ = ["AudioPreprocessor", "DEFAULT_FILTER_CHAIN"]
