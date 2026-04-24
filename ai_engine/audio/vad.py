from loguru import logger

try:
    from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
except ImportError:
    load_silero_vad = None
    logger.warning(
        "silero-vad not installed, VoiceActivityDetector will be unavailable"
    )


class VoiceActivityDetector:
    def __init__(self):
        if load_silero_vad is None:
            raise RuntimeError("silero-vad not installed")
        self.model = load_silero_vad(onnx=False)

    def detect(self, audio_path: str, sample_rate: int = 16000) -> list[dict]:
        wav = read_audio(audio_path, sampling_rate=sample_rate)
        timestamps = get_speech_timestamps(
            wav,
            self.model,
            sampling_rate=sample_rate,
            return_seconds=True,
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=100,
            speech_pad_ms=30,
        )
        logger.info(f"VAD detected {len(timestamps)} speech segments")
        return [{"start": t["start"], "end": t["end"]} for t in timestamps]

    def segment_audio(
        self, waveform, segments: list[dict], sample_rate: int = 16000
    ) -> list[dict]:
        results = []
        for seg in segments:
            start_sample = int(seg["start"] * sample_rate)
            end_sample = int(seg["end"] * sample_rate)
            segment_wav = waveform[start_sample:end_sample]
            results.append(
                {
                    "start": seg["start"],
                    "end": seg["end"],
                    "waveform": segment_wav,
                }
            )
        return results
