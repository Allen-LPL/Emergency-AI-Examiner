import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch


@dataclass
class FakeDiarizationSegment:
    start: float
    end: float
    speaker: str


def load_diarizer_module():
    module_path = Path(__file__).resolve().parents[3] / "ai_engine/audio/diarizer.py"
    fake_loguru = types.SimpleNamespace(
        logger=types.SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        )
    )
    fake_types_module = types.SimpleNamespace(DiarizationSegment=FakeDiarizationSegment)
    fake_pyannote_audio = types.SimpleNamespace(Pipeline=None)
    class FakeTensor:
        ndim = 2

        def transpose(self, dim0, dim1):
            return self

        def contiguous(self):
            return self

    fake_torch = types.SimpleNamespace(
        as_tensor=lambda waveform, dtype=None: FakeTensor(),
        cuda=types.SimpleNamespace(is_available=lambda: False),
        device=lambda device: device,
        float32="float32",
    )
    fake_soundfile = types.SimpleNamespace(
        read=lambda audio_path, dtype="float32", always_2d=True: (
            [[0.0], [0.1], [0.0]],
            16000,
        )
    )
    spec = importlib.util.spec_from_file_location("diarizer_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load diarizer module")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "loguru": fake_loguru,
            "torch": fake_torch,
            "soundfile": fake_soundfile,
            "pyannote.audio": fake_pyannote_audio,
            "ai_engine.audio.types": fake_types_module,
        },
    ):
        spec.loader.exec_module(module)
    return module


diarizer_module = load_diarizer_module()


class FakeTurn:
    start = 0.1
    end = 1.2


class FakeDiarization:
    def itertracks(self, yield_label=False):
        yield FakeTurn(), None, "SPEAKER_00"


class FakePipeline:
    def __init__(self):
        self.calls = []

    def __call__(self, audio_input, **kwargs):
        self.calls.append((audio_input, kwargs))
        return FakeDiarization()


class SpeakerDiarizerTests(unittest.TestCase):
    def test_diarize_passes_waveform_dict_to_pyannote(self):
        pipeline = FakePipeline()
        diarizer = diarizer_module.SpeakerDiarizer.__new__(
            diarizer_module.SpeakerDiarizer
        )
        diarizer.pipeline = pipeline
        diarizer.num_speakers = 3

        segments = diarizer.diarize("audio_preprocessed.wav")

        self.assertEqual(len(segments), 1)
        audio_input, kwargs = pipeline.calls[0]
        self.assertIsInstance(audio_input, dict)
        self.assertEqual(set(audio_input), {"waveform", "sample_rate"})
        self.assertEqual(audio_input["sample_rate"], 16000)
        self.assertEqual(kwargs, {"num_speakers": 3})


if __name__ == "__main__":
    unittest.main()
