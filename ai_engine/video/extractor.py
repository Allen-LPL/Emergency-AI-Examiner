import cv2
import numpy as np
from loguru import logger


class FrameExtractor:
    def __init__(self, target_fps: int = 10):
        self.target_fps = target_fps

    def get_video_info(self, video_path: str) -> dict:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        info = {
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        }
        info["duration"] = info["total_frames"] / info["fps"] if info["fps"] > 0 else 0
        cap.release()
        return info

    def extract_frames(self, video_path: str) -> list[dict]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        source_fps = cap.get(cv2.CAP_PROP_FPS)
        if source_fps <= 0:
            cap.release()
            raise RuntimeError(f"Invalid FPS in video: {video_path}")

        frame_interval = max(1, int(source_fps / self.target_fps))
        frames = []
        frame_idx = 0

        logger.info(
            f"Extracting frames at {self.target_fps}fps "
            f"(source: {source_fps:.1f}fps, interval: {frame_interval})"
        )

        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            if frame_idx % frame_interval == 0:
                timestamp = frame_idx / source_fps
                frames.append(
                    {
                        "frame_idx": frame_idx,
                        "timestamp": round(timestamp, 3),
                        "frame": frame,
                    }
                )

            frame_idx += 1

        cap.release()
        logger.info(f"Extracted {len(frames)} frames from {frame_idx} total")
        return frames
