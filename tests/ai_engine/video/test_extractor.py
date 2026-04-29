import unittest
from unittest.mock import patch

from ai_engine.video.extractor import FrameExtractor


class FrameExtractorTests(unittest.TestCase):
    def test_extract_frames_adaptive_uses_duration_cap_and_restores_target_fps(self):
        extractor = FrameExtractor(target_fps=10)
        observed_target_fps = []

        def fake_extract_frames(video_path):
            observed_target_fps.append(extractor.target_fps)
            return [{"frame_idx": 0, "timestamp": 0.0, "frame": None}]

        with (
            patch.object(extractor, "get_video_info", return_value={"duration": 1000}),
            patch.object(extractor, "extract_frames", side_effect=fake_extract_frames),
        ):
            frames = extractor.extract_frames_adaptive("demo.mp4", max_frames=600)

        self.assertEqual(len(frames), 1)
        self.assertEqual(observed_target_fps, [0.6])
        self.assertEqual(extractor.target_fps, 10)

    def test_extract_frames_adaptive_falls_back_for_non_positive_duration(self):
        extractor = FrameExtractor(target_fps=4)
        called = []

        def fake_extract_frames(video_path):
            called.append(video_path)
            return [{"frame_idx": 1, "timestamp": 1.0, "frame": None}]

        with (
            patch.object(extractor, "get_video_info", return_value={"duration": 0}),
            patch.object(extractor, "extract_frames", side_effect=fake_extract_frames),
        ):
            frames = extractor.extract_frames_adaptive("zero.mp4", max_frames=600)

        self.assertEqual(called, ["zero.mp4"])
        self.assertEqual(frames[0]["frame_idx"], 1)
        self.assertEqual(extractor.target_fps, 4)

    def test_extract_frames_adaptive_trims_overshoot_to_max_frames(self):
        extractor = FrameExtractor(target_fps=10)

        fake_frames = [
            {"frame_idx": idx, "timestamp": float(idx), "frame": None}
            for idx in range(750)
        ]

        with (
            patch.object(extractor, "get_video_info", return_value={"duration": 1000}),
            patch.object(extractor, "extract_frames", return_value=fake_frames),
        ):
            frames = extractor.extract_frames_adaptive("long.mp4", max_frames=600)

        self.assertEqual(len(frames), 600)
        self.assertEqual(frames[0]["frame_idx"], 0)
        self.assertEqual(frames[-1]["frame_idx"], 599)


if __name__ == "__main__":
    unittest.main()
