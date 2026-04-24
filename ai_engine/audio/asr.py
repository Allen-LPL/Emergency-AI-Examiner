from loguru import logger

try:
    from funasr import AutoModel
except ImportError:
    AutoModel = None
    logger.warning("funasr not installed, SpeechRecognizer will be unavailable")


class SpeechRecognizer:
    def __init__(
        self,
        model_name: str = "iic/SenseVoiceSmall",
        vad_model: str = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        device: str = "cuda:0",
    ):
        if AutoModel is None:
            raise RuntimeError("funasr not installed")

        logger.info(f"Loading ASR model: {model_name}")
        try:
            self.model = AutoModel(
                model=model_name,
                vad_model=vad_model,
                punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                device=device,
                hub="ms",
            )
        except Exception as e:
            logger.warning(f"Failed to load with GPU ({e}), falling back to CPU")
            self.model = AutoModel(
                model=model_name,
                vad_model=vad_model,
                punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                device="cpu",
                hub="ms",
            )

    def transcribe(self, audio_path: str) -> list[dict]:
        logger.info(f"Transcribing: {audio_path}")
        try:
            results = self.model.generate(input=audio_path)
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            return []

        segments = []
        for item in results:
            text = item.get("text", "")
            timestamps = item.get("timestamp", [])

            if timestamps and len(timestamps) >= 2:
                start = (
                    timestamps[0][0] / 1000.0
                    if isinstance(timestamps[0], list)
                    else 0.0
                )
                end = (
                    timestamps[-1][1] / 1000.0
                    if isinstance(timestamps[-1], list)
                    else 0.0
                )
            else:
                start = 0.0
                end = 0.0

            if text.strip():
                segments.append(
                    {
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "text": text.strip(),
                        "confidence": 0.9,
                    }
                )

        logger.info(f"Transcribed {len(segments)} segments")
        return segments

    def transcribe_segments(
        self, audio_path: str, vad_segments: list[dict]
    ) -> list[dict]:
        all_segments = self.transcribe(audio_path)
        return all_segments
