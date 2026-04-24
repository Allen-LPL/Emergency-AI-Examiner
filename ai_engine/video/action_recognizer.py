import numpy as np
from loguru import logger

KP_LEFT_SHOULDER = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_HIP = 11
KP_RIGHT_HIP = 12


class ActionRecognizer:
    def __init__(self, window_size: int = 15):
        self.window_size = window_size

    def recognize_from_poses(
        self, pose_sequence: list[dict], timestamps: list[float]
    ) -> list[dict]:
        if len(pose_sequence) < 2:
            return []

        events = []
        events.extend(self._detect_running(pose_sequence, timestamps))
        events.extend(self._detect_chest_compression(pose_sequence, timestamps))
        events.extend(self._detect_kneeling(pose_sequence, timestamps))
        return sorted(events, key=lambda e: e["time"])

    def _detect_running(
        self, pose_sequence: list[dict], timestamps: list[float]
    ) -> list[dict]:
        events = []
        for i in range(1, len(pose_sequence)):
            prev_bbox = pose_sequence[i - 1].get("bbox", [])
            curr_bbox = pose_sequence[i].get("bbox", [])
            if len(prev_bbox) < 4 or len(curr_bbox) < 4:
                continue

            prev_center_x = (prev_bbox[0] + prev_bbox[2]) / 2
            curr_center_x = (curr_bbox[0] + curr_bbox[2]) / 2
            dt = (
                timestamps[i] - timestamps[i - 1]
                if timestamps[i] != timestamps[i - 1]
                else 0.1
            )
            speed = abs(curr_center_x - prev_center_x) / dt

            if speed > 200:
                events.append(
                    {
                        "time": timestamps[i],
                        "action": "running",
                        "confidence": min(speed / 500, 1.0),
                        "actor_track_id": pose_sequence[i].get("track_id"),
                    }
                )
        return events

    def _detect_chest_compression(
        self, pose_sequence: list[dict], timestamps: list[float]
    ) -> list[dict]:
        events = []
        shoulder_y_history = []

        for pose_data in pose_sequence:
            kps = pose_data.get("keypoints")
            if kps is None or (isinstance(kps, np.ndarray) and kps.shape[0] < 17):
                shoulder_y_history.append(None)
                continue
            l_sh = kps[KP_LEFT_SHOULDER]
            r_sh = kps[KP_RIGHT_SHOULDER]
            if l_sh[2] > 0.3 and r_sh[2] > 0.3:
                shoulder_y_history.append((l_sh[1] + r_sh[1]) / 2)
            else:
                shoulder_y_history.append(None)

        for i in range(self.window_size, len(shoulder_y_history)):
            window = shoulder_y_history[i - self.window_size : i]
            valid = [v for v in window if v is not None]
            if len(valid) < self.window_size * 0.6:
                continue

            oscillations = 0
            for j in range(2, len(valid)):
                if (valid[j] - valid[j - 1]) * (valid[j - 1] - valid[j - 2]) < 0:
                    oscillations += 1

            amplitude = max(valid) - min(valid) if valid else 0
            is_compression = oscillations >= 4 and amplitude > 15

            if is_compression:
                events.append(
                    {
                        "time": timestamps[i],
                        "action": "chest_compression",
                        "confidence": min(oscillations / 10, 0.95),
                        "actor_track_id": pose_sequence[i].get("track_id"),
                    }
                )

        return self._deduplicate_events(events, min_gap=2.0)

    def _detect_kneeling(
        self, pose_sequence: list[dict], timestamps: list[float]
    ) -> list[dict]:
        events = []
        for i, pose_data in enumerate(pose_sequence):
            kps = pose_data.get("keypoints")
            if kps is None or (isinstance(kps, np.ndarray) and kps.shape[0] < 17):
                continue
            hip_y = (kps[KP_LEFT_HIP][1] + kps[KP_RIGHT_HIP][1]) / 2
            shoulder_y = (kps[KP_LEFT_SHOULDER][1] + kps[KP_RIGHT_SHOULDER][1]) / 2
            bbox = pose_data.get("bbox", [0, 0, 0, 100])
            bbox_height = bbox[3] - bbox[1] if len(bbox) >= 4 else 100

            hip_ratio = (hip_y - shoulder_y) / bbox_height if bbox_height > 0 else 0
            if hip_ratio > 0.35:
                events.append(
                    {
                        "time": timestamps[i],
                        "action": "kneeling",
                        "confidence": 0.7,
                        "actor_track_id": pose_data.get("track_id"),
                    }
                )

        return self._deduplicate_events(events, min_gap=3.0)

    def detect_chest_compression_cycles(
        self, pose_sequence: list[dict], timestamps: list[float]
    ) -> list[dict]:
        cycles = []
        in_cycle = False
        cycle_start = 0.0

        for i in range(1, len(pose_sequence)):
            kps = pose_sequence[i].get("keypoints")
            if kps is None or (isinstance(kps, np.ndarray) and kps.shape[0] < 17):
                continue

            l_sh = kps[KP_LEFT_SHOULDER]
            r_sh = kps[KP_RIGHT_SHOULDER]
            if l_sh[2] < 0.3 or r_sh[2] < 0.3:
                continue
            shoulder_y = (l_sh[1] + r_sh[1]) / 2

            prev_kps = pose_sequence[i - 1].get("keypoints")
            if prev_kps is None or (
                isinstance(prev_kps, np.ndarray) and prev_kps.shape[0] < 17
            ):
                continue
            prev_shoulder_y = (
                prev_kps[KP_LEFT_SHOULDER][1] + prev_kps[KP_RIGHT_SHOULDER][1]
            ) / 2

            going_down = shoulder_y > prev_shoulder_y + 3

            if going_down and not in_cycle:
                in_cycle = True
                cycle_start = timestamps[i]
            elif not going_down and in_cycle and shoulder_y < prev_shoulder_y - 3:
                in_cycle = False
                cycle_end = timestamps[i]
                duration = cycle_end - cycle_start
                if 0.3 < duration < 2.0:
                    rate = 60.0 / duration if duration > 0 else 0
                    cycles.append(
                        {
                            "start_time": cycle_start,
                            "end_time": cycle_end,
                            "rate_per_min": round(rate, 1),
                        }
                    )

        return cycles

    @staticmethod
    def _deduplicate_events(events: list[dict], min_gap: float = 2.0) -> list[dict]:
        if not events:
            return events
        deduped = [events[0]]
        for event in events[1:]:
            if event["time"] - deduped[-1]["time"] >= min_gap:
                deduped.append(event)
            elif event["confidence"] > deduped[-1]["confidence"]:
                deduped[-1] = event
        return deduped
