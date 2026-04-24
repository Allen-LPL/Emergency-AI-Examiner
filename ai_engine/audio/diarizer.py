import torch
from loguru import logger

try:
    from pyannote.audio import Pipeline as PyannotePipeline
except ImportError:
    PyannotePipeline = None
    logger.warning("pyannote.audio not installed, SpeakerDiarizer will be unavailable")


class SpeakerDiarizer:
    def __init__(
        self,
        hf_token: str | None = None,
        device: str = "cuda:0",
        max_speakers: int = 4,
    ):
        self.max_speakers = max_speakers
        self.pipeline = None

        if PyannotePipeline is None:
            logger.warning("pyannote.audio not available, diarization disabled")
            return

        if not hf_token:
            logger.warning("HuggingFace token not provided, diarization disabled")
            return

        try:
            self.pipeline = PyannotePipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
            )
            if torch.cuda.is_available() and "cuda" in device:
                self.pipeline.to(torch.device(device))
            logger.info("Speaker diarization pipeline loaded")
        except Exception as e:
            logger.warning(f"Failed to load diarization pipeline: {e}")
            self.pipeline = None

    def diarize(self, audio_path: str) -> list[dict]:
        if self.pipeline is None:
            logger.info("Diarization unavailable, returning empty result")
            return []

        try:
            diarization = self.pipeline(
                audio_path,
                min_speakers=1,
                max_speakers=self.max_speakers,
            )
        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return []

        segments = []
        for speech_turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                {
                    "start": round(speech_turn.start, 3),
                    "end": round(speech_turn.end, 3),
                    "speaker": speaker,
                }
            )

        logger.info(
            f"Diarization: {len(segments)} segments, speakers: {set(s['speaker'] for s in segments)}"
        )
        return segments

    def assign_speakers(
        self, transcription: list[dict], diarization: list[dict]
    ) -> list[dict]:
        if not diarization:
            return transcription

        for segment in transcription:
            seg_start = segment.get("start", 0)
            seg_end = segment.get("end", 0)
            seg_mid = (seg_start + seg_end) / 2

            best_speaker = None
            best_overlap = 0

            for d_seg in diarization:
                overlap_start = max(seg_start, d_seg["start"])
                overlap_end = min(seg_end, d_seg["end"])
                overlap = max(0, overlap_end - overlap_start)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = d_seg["speaker"]

            segment["speaker"] = best_speaker

        return transcription
