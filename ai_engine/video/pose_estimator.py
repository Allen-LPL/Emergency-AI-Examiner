import numpy as np
from loguru import logger

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None
    logger.warning("ultralytics not installed, PoseEstimator will be unavailable")

COCO_KEYPOINTS = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

KP_LEFT_SHOULDER = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_ELBOW = 7
KP_RIGHT_ELBOW = 8
KP_LEFT_WRIST = 9
KP_RIGHT_WRIST = 10
KP_LEFT_HIP = 11
KP_RIGHT_HIP = 12
KP_LEFT_KNEE = 13
KP_RIGHT_KNEE = 14


class PoseEstimator:
    def __init__(self, model_path: str = "yolov8n-pose.pt", device: str = "cuda:0"):
        if YOLO is None:
            raise RuntimeError("ultralytics package not installed")
        self.model = YOLO(model_path)
        self.model.to(device)

    def estimate(self, frame: np.ndarray) -> list[dict]:
        results = self.model(frame, verbose=False)
        poses = []
        for result in results:
            if result.keypoints is None:
                continue
            kps_data = result.keypoints.data.cpu().numpy()
            boxes = result.boxes
            for i in range(len(kps_data)):
                keypoints = kps_data[i]
                bbox = boxes.xyxy[i].cpu().numpy().tolist() if boxes is not None else []
                conf = float(boxes.conf[i].cpu().item()) if boxes is not None else 0.0
                poses.append(
                    {
                        "keypoints": keypoints,
                        "bbox": bbox,
                        "confidence": round(conf, 3),
                    }
                )
        return poses

    def detect_compression_pose(self, keypoints: np.ndarray) -> bool:
        if keypoints.shape[0] < 17:
            return False

        l_shoulder = keypoints[KP_LEFT_SHOULDER]
        r_shoulder = keypoints[KP_RIGHT_SHOULDER]
        l_hip = keypoints[KP_LEFT_HIP]
        r_hip = keypoints[KP_RIGHT_HIP]
        l_wrist = keypoints[KP_LEFT_WRIST]
        r_wrist = keypoints[KP_RIGHT_WRIST]
        l_knee = keypoints[KP_LEFT_KNEE]
        r_knee = keypoints[KP_RIGHT_KNEE]

        min_confidence = 0.3
        required_points = [l_shoulder, r_shoulder, l_hip, r_hip, l_wrist, r_wrist]
        if any(p[2] < min_confidence for p in required_points):
            return False

        shoulder_y = (l_shoulder[1] + r_shoulder[1]) / 2
        hip_y = (l_hip[1] + r_hip[1]) / 2
        wrist_y = (l_wrist[1] + r_wrist[1]) / 2
        knee_y = (l_knee[1] + r_knee[1]) / 2

        shoulders_above_hips = shoulder_y < hip_y
        wrists_below_shoulders = wrist_y > shoulder_y
        kneeling = knee_y > hip_y and (knee_y - hip_y) < (hip_y - shoulder_y) * 2

        return shoulders_above_hips and wrists_below_shoulders and kneeling

    def detect_ventilation_pose(self, keypoints: np.ndarray) -> bool:
        if keypoints.shape[0] < 17:
            return False

        l_wrist = keypoints[KP_LEFT_WRIST]
        r_wrist = keypoints[KP_RIGHT_WRIST]
        nose = keypoints[0]

        min_confidence = 0.3
        if any(p[2] < min_confidence for p in [l_wrist, r_wrist, nose]):
            return False

        wrist_center_y = (l_wrist[1] + r_wrist[1]) / 2
        hands_near_face = abs(wrist_center_y - nose[1]) < 100

        wrist_center_x = (l_wrist[0] + r_wrist[0]) / 2
        hands_near_head_x = abs(wrist_center_x - nose[0]) < 150

        return hands_near_face and hands_near_head_x
