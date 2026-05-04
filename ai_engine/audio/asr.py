import numpy as np
import soundfile as sf
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
                disable_update=True,
            )
        except Exception as e:
            logger.warning(f"Failed to load with GPU ({e}), falling back to CPU")
            self.model = AutoModel(
                model=model_name,
                vad_model=vad_model,
                punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                device="cpu",
                hub="ms",
                disable_update=True,
            )

        self._model_no_vad = None
        self._model_name = model_name
        self._device = device

    def _get_model_no_vad(self):
        if self._model_no_vad is None:
            try:
                self._model_no_vad = AutoModel(
                    model=self._model_name,
                    device=self._device,
                    hub="ms",
                    disable_update=True,
                )
            except Exception:
                self._model_no_vad = AutoModel(
                    model=self._model_name,
                    device="cpu",
                    hub="ms",
                    disable_update=True,
                )
        return self._model_no_vad

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
        if not vad_segments:
            return self.transcribe(audio_path)

        logger.info(f"Transcribing {len(vad_segments)} VAD segments from {audio_path}")

        try:
            audio_data, sample_rate = sf.read(audio_path)
            if len(audio_data.shape) > 1:
                audio_data = audio_data[:, 0]
        except Exception as e:
            logger.error(f"Failed to read audio file: {e}")
            return self.transcribe(audio_path)

        model = self._get_model_no_vad()
        all_segments = []

        for i, vad_seg in enumerate(vad_segments):
            start_sec = vad_seg.get("start", 0)
            end_sec = vad_seg.get("end", 0)
            if end_sec <= start_sec:
                continue

            start_sample = int(start_sec * sample_rate)
            end_sample = int(end_sec * sample_rate)
            chunk = audio_data[start_sample:end_sample]

            if len(chunk) < sample_rate * 0.1:
                continue

            try:
                results = model.generate(
                    input=chunk.astype(np.float32),
                    fs=sample_rate,
                )
            except Exception as e:
                logger.warning(
                    f"ASR failed for segment {i} [{start_sec:.1f}-{end_sec:.1f}]: {e}"
                )
                continue

            for item in results:
                text = item.get("text", "")
                if not text.strip():
                    continue

                timestamps = item.get("timestamp", [])
                if timestamps and len(timestamps) >= 2:
                    seg_start = (
                        timestamps[0][0] / 1000.0
                        if isinstance(timestamps[0], list)
                        else 0.0
                    )
                    seg_end = (
                        timestamps[-1][1] / 1000.0
                        if isinstance(timestamps[-1], list)
                        else 0.0
                    )
                else:
                    seg_start = 0.0
                    seg_end = end_sec - start_sec

                all_segments.append(
                    {
                        "start": round(start_sec + seg_start, 3),
                        "end": round(start_sec + seg_end, 3),
                        "text": text.strip(),
                        "confidence": 0.9,
                    }
                )

        logger.info(
            f"Transcribed {len(all_segments)} segments from {len(vad_segments)} VAD segments"
        )
        return all_segments
