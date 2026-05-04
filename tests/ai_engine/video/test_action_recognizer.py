import importlib.util
import sys
import types
import unittest
from pathlib import Path

sys.modules.setdefault("numpy", types.SimpleNamespace(ndarray=tuple))
sys.modules.setdefault(
    "loguru",
    types.SimpleNamespace(
        logger=types.SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
        )
    ),
)

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "ai_engine" / "video" / "action_recognizer.py"
)
SPEC = importlib.util.spec_from_file_location(
    "test_action_recognizer_module", MODULE_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
ActionRecognizer = MODULE.ActionRecognizer


class ActionRecognizerTests(unittest.TestCase):
    def _make_keypoints(self):
        keypoints = [[0.0, 0.0, 0.9] for _ in range(17)]
        return keypoints

    def test_detect_ventilation_pose_detects_hands_near_face(self):
        recognizer = ActionRecognizer()
        keypoints = self._make_keypoints()
        keypoints[0] = [100, 100, 0.9]
        keypoints[9] = [110, 110, 0.9]
        keypoints[10] = [112, 108, 0.9]
        pose_sequence = [
            {"keypoints": keypoints, "bbox": [0, 0, 0, 240], "track_id": 1}
        ]

        events = recognizer._detect_ventilation_pose(pose_sequence, [5.0])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "ventilation_pose")

    def test_detect_standing_nearby_detects_expected_pose_ratio(self):
        recognizer = ActionRecognizer()
        keypoints = self._make_keypoints()
        keypoints[5] = [80, 100, 0.9]
        keypoints[6] = [120, 100, 0.9]
        keypoints[11] = [90, 140, 0.9]
        keypoints[12] = [110, 140, 0.9]
        pose_sequence = [
            {"keypoints": keypoints, "bbox": [0, 0, 200, 200], "track_id": 7}
        ]

        events = recognizer._detect_standing_nearby(pose_sequence, [8.0])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "standing_nearby")

    def test_recognize_from_poses_includes_new_event_types(self):
        recognizer = ActionRecognizer()
        first = self._make_keypoints()
        second = self._make_keypoints()

        for keypoints in [first, second]:
            keypoints[0] = [100, 100, 0.9]
            keypoints[5] = [80, 100, 0.9]
            keypoints[6] = [120, 100, 0.9]
            keypoints[9] = [110, 110, 0.9]
            keypoints[10] = [112, 108, 0.9]
            keypoints[11] = [90, 140, 0.9]
            keypoints[12] = [110, 140, 0.9]

        pose_sequence = [
            {"keypoints": first, "bbox": [0, 0, 200, 200], "track_id": 1},
            {"keypoints": second, "bbox": [0, 0, 200, 200], "track_id": 1},
        ]

        events = recognizer.recognize_from_poses(pose_sequence, [1.0, 2.0])

        actions = {event["action"] for event in events}
        self.assertIn("ventilation_pose", actions)
        self.assertIn("standing_nearby", actions)


if __name__ == "__main__":
    unittest.main()
