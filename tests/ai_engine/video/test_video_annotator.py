import unittest
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch


def load_video_annotator_module():
    module_path = (
        Path(__file__).resolve().parents[3] / "ai_engine/video/video_annotator.py"
    )
    fake_cv2 = types.SimpleNamespace(
        CAP_PROP_FPS="CAP_PROP_FPS",
        CAP_PROP_FRAME_WIDTH="CAP_PROP_FRAME_WIDTH",
        CAP_PROP_FRAME_HEIGHT="CAP_PROP_FRAME_HEIGHT",
        CAP_PROP_FRAME_COUNT="CAP_PROP_FRAME_COUNT",
        FONT_HERSHEY_SIMPLEX="FONT_HERSHEY_SIMPLEX",
        LINE_AA="LINE_AA",
        VideoCapture=None,
        VideoWriter=None,
        VideoWriter_fourcc=None,
    )
    fake_numpy = types.SimpleNamespace(ndarray=object, array=lambda value: value)
    fake_loguru = types.SimpleNamespace(
        logger=types.SimpleNamespace(info=lambda *args, **kwargs: None)
    )
    spec = importlib.util.spec_from_file_location(
        "video_annotator_under_test", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load video_annotator module")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules, {"cv2": fake_cv2, "numpy": fake_numpy, "loguru": fake_loguru}
    ):
        spec.loader.exec_module(module)
    return module


video_annotator_module = load_video_annotator_module()
VideoAnnotator = video_annotator_module.VideoAnnotator


class FakeCapture:
    def __init__(self, path):
        self.path = path
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        values = {
            video_annotator_module.cv2.CAP_PROP_FPS: 25.0,
            video_annotator_module.cv2.CAP_PROP_FRAME_WIDTH: 640,
            video_annotator_module.cv2.CAP_PROP_FRAME_HEIGHT: 480,
            video_annotator_module.cv2.CAP_PROP_FRAME_COUNT: 0,
        }
        return values[prop]

    def read(self):
        return False, None

    def release(self):
        self.released = True


class FakeWriter:
    def __init__(self, path, fourcc, fps, size):
        self.path = path
        self.fourcc = fourcc
        self.fps = fps
        self.size = size
        self.released = False

    def isOpened(self):
        return True

    def write(self, frame):
        raise AssertionError("test fixture should not write frames")

    def release(self):
        self.released = True


class VideoAnnotatorTests(unittest.TestCase):
    def test_generate_writes_mp4_with_h264_fourcc(self):
        requested_codecs = []
        created_writers = []

        def fake_fourcc(*chars):
            codec = "".join(chars)
            requested_codecs.append(codec)
            return codec

        def fake_video_writer(path, fourcc, fps, size):
            writer = FakeWriter(path, fourcc, fps, size)
            created_writers.append(writer)
            return writer

        with (
            patch.object(video_annotator_module.cv2, "VideoCapture", FakeCapture),
            patch.object(video_annotator_module.cv2, "VideoWriter", fake_video_writer),
            patch.object(video_annotator_module.cv2, "VideoWriter_fourcc", fake_fourcc),
        ):
            result = VideoAnnotator().generate(
                video_path="input.mp4",
                output_path="/tmp/input_annotated.mp4",
                frame_results=[],
                action_events=[],
                transcription=[],
            )

        self.assertEqual(requested_codecs, ["avc1"])
        self.assertEqual(created_writers[0].fourcc, "avc1")
        self.assertEqual(Path(result).name, "input_annotated.mp4")


if __name__ == "__main__":
    unittest.main()
