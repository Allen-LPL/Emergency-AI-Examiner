import numpy as np
from loguru import logger

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None
    logger.warning("ultralytics not installed, ObjectDetector will be unavailable")

EQUIPMENT_CLASS_MAP = {
    "backpack": "medicine_box",
    "suitcase": "medicine_box",
    "handbag": "medicine_box",
    "cell phone": "monitor_device",
    "laptop": "monitor_device",
}

PERSON_CLASS_ID = 0


class ObjectDetector:
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        device: str = "cuda:0",
        conf_threshold: float = 0.3,
    ):
        if YOLO is None:
            raise RuntimeError("ultralytics package not installed")
        self.model = YOLO(model_path)
        self.model.to(device)
        self.conf_threshold = conf_threshold
        self.device = device

    def detect(self, frame: np.ndarray) -> list[dict]:
        results = self.model(frame, conf=self.conf_threshold, verbose=False)
        detections = []
        for result in results:
            boxes = result.boxes
            for i in range(len(boxes)):
                bbox = boxes.xyxy[i].cpu().numpy().tolist()
                cls_id = int(boxes.cls[i].cpu().item())
                cls_name = result.names[cls_id]
                conf = float(boxes.conf[i].cpu().item())
                detections.append(
                    {
                        "bbox": bbox,
                        "class_name": cls_name,
                        "class_id": cls_id,
                        "confidence": round(conf, 3),
                    }
                )
        return detections

    def detect_persons(self, frame: np.ndarray) -> list[dict]:
        results = self.model(
            frame, conf=self.conf_threshold, classes=[PERSON_CLASS_ID], verbose=False
        )
        persons = []
        for result in results:
            boxes = result.boxes
            for i in range(len(boxes)):
                bbox = boxes.xyxy[i].cpu().numpy().tolist()
                conf = float(boxes.conf[i].cpu().item())
                persons.append({"bbox": bbox, "confidence": round(conf, 3)})
        return persons

    def detect_equipment(self, frame: np.ndarray) -> list[dict]:
        all_detections = self.detect(frame)
        equipment = []
        for det in all_detections:
            mapped_name = EQUIPMENT_CLASS_MAP.get(det["class_name"])
            if mapped_name:
                equipment.append(
                    {
                        "bbox": det["bbox"],
                        "class_name": mapped_name,
                        "original_class": det["class_name"],
                        "confidence": det["confidence"],
                    }
                )
        return equipment
