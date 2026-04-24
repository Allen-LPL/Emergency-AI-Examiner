import numpy as np
from loguru import logger

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None
    logger.warning("ultralytics not installed, PersonTracker will be unavailable")


class PersonTracker:
    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cuda:0"):
        if YOLO is None:
            raise RuntimeError("ultralytics package not installed")
        self.model = YOLO(model_path)
        self.model.to(device)

    def track(self, frame: np.ndarray, conf: float = 0.3) -> list[dict]:
        results = self.model.track(
            frame,
            conf=conf,
            classes=[0],
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )

        tracked = []
        for result in results:
            boxes = result.boxes
            if boxes.id is None:
                continue
            for i in range(len(boxes)):
                bbox = boxes.xyxy[i].cpu().numpy().tolist()
                track_id = int(boxes.id[i].cpu().item())
                conf_val = float(boxes.conf[i].cpu().item())
                tracked.append(
                    {
                        "track_id": track_id,
                        "bbox": bbox,
                        "confidence": round(conf_val, 3),
                    }
                )
        return tracked

    def reset(self):
        self.model.predictor = None
