# pyright: reportMissingImports=false
from loguru import logger

try:
    import numpy as np
    from ultralytics import YOLO

    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    YOLO = None
    logger.warning("ultralytics/numpy not installed, PoseDetector unavailable")


class PoseDetector:
    def __init__(self, model_path: str = "yolov8n-pose.pt", device: str = "cuda:0"):
        if not _AVAILABLE or YOLO is None:
            raise RuntimeError("ultralytics not installed")
        self.model = YOLO(model_path)
        self.model.to(device)
        self.device = device
        logger.info(f"PoseDetector loaded: {model_path} on {device}")

    def detect_batch(self, frames: list[dict], progress_fn=None) -> list[dict]:
        results = []
        total = len(frames)
        for i, frame_data in enumerate(frames):
            frame_result = self._process_frame(frame_data)
            results.append(frame_result)
            if progress_fn and (i % 50 == 0 or i == total - 1):
                progress_fn(i + 1, total)
        return results

    def _process_frame(self, frame_data: dict) -> dict:
        frame = frame_data["frame"]
        timestamp = frame_data["timestamp"]
        if self.model is None:
            return {"timestamp": timestamp, "persons": []}
        try:
            yolo_results = self.model(frame, verbose=False)
            persons = []
            for result in yolo_results:
                boxes = result.boxes
                keypoints_data = result.keypoints
                if boxes is None:
                    continue
                for i in range(len(boxes)):
                    bbox = boxes.xyxy[i].cpu().numpy().tolist()
                    conf = float(boxes.conf[i].cpu().item())
                    kps = None
                    if keypoints_data is not None and i < len(keypoints_data.data):
                        kps = keypoints_data.data[i].cpu().numpy()
                    persons.append(
                        {
                            "bbox": bbox,
                            "confidence": round(conf, 3),
                            "keypoints": kps,
                        }
                    )
            return {"timestamp": timestamp, "persons": persons}
        except Exception as exc:
            logger.debug(f"Frame at {timestamp}s detection error: {exc}")
            return {"timestamp": timestamp, "persons": []}

    def release(self):
        if self.model is not None:
            del self.model
        self.model = None
        logger.info("PoseDetector released")
