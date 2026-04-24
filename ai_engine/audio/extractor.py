import subprocess
from pathlib import Path

import numpy as np
from loguru import logger

try:
    import soundfile as sf
except ImportError:
    sf = None


class AudioExtractor:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate

    def extract_from_video(
        self, video_path: str, output_path: str | None = None
    ) -> str:
        if output_path is None:
            output_path = str(Path(video_path).with_suffix(".wav"))

        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(self.sample_rate),
            "-ac",
            "1",
            "-y",
            output_path,
        ]

        logger.info(f"Extracting audio from {video_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")

        logger.info(f"Audio saved to {output_path}")
        return output_path

    def load_audio(self, audio_path: str) -> tuple[np.ndarray, int]:
        if sf is None:
            raise RuntimeError("soundfile not installed")
        waveform, sr = sf.read(audio_path, dtype="float32")
        if sr != self.sample_rate:
            logger.warning(f"Sample rate mismatch: {sr} != {self.sample_rate}")
        return waveform, sr
