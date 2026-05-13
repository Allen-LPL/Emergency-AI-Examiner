# pyright: reportMissingImports=false
"""视频标注器: 将姿态估计、关键点、动作识别、语音识别结果叠加到原始视频上，生成标注视频。"""

import bisect
from pathlib import Path

import cv2
import numpy as np
from loguru import logger

SKELETON_CONNECTIONS = [
    (0, 1),
    (0, 2),  # nose -> eyes
    (1, 3),
    (2, 4),  # eyes -> ears
    (5, 6),  # left_shoulder -> right_shoulder
    (5, 7),
    (7, 9),  # left arm
    (6, 8),
    (8, 10),  # right arm
    (5, 11),
    (6, 12),  # shoulders -> hips
    (11, 12),  # left_hip -> right_hip
    (11, 13),
    (13, 15),  # left leg
    (12, 14),
    (14, 16),  # right leg
]

# 左侧肢体用蓝色系，右侧用红色系，中轴用绿色系
BONE_COLORS = {
    (0, 1): (255, 200, 0),
    (0, 2): (0, 200, 255),
    (1, 3): (255, 200, 0),
    (2, 4): (0, 200, 255),
    (5, 6): (0, 255, 128),
    (5, 7): (255, 160, 0),
    (7, 9): (255, 100, 0),
    (6, 8): (0, 160, 255),
    (8, 10): (0, 100, 255),
    (5, 11): (255, 160, 0),
    (6, 12): (0, 160, 255),
    (11, 12): (0, 255, 128),
    (11, 13): (255, 160, 0),
    (13, 15): (255, 100, 0),
    (12, 14): (0, 160, 255),
    (14, 16): (0, 100, 255),
}

KEYPOINT_COLOR = (0, 255, 255)
BBOX_COLOR = (0, 255, 0)

ACTION_LABELS_ZH = {
    "chest_compression": "胸外按压",
    "ventilation_pose": "球囊通气",
    "running": "跑步",
    "kneeling": "跪姿",
    "standing_nearby": "站立观察",
}

ACTION_COLORS = {
    "chest_compression": (0, 0, 255),
    "ventilation_pose": (255, 128, 0),
    "running": (0, 200, 200),
    "kneeling": (200, 0, 200),
    "standing_nearby": (200, 200, 0),
}


class VideoAnnotator:
    """将 AI 分析结果叠加渲染到原始视频帧上，输出标注视频文件。"""

    def __init__(
        self,
        keypoint_threshold: float = 0.3,
        keypoint_radius: int = 4,
        bone_thickness: int = 2,
        bbox_thickness: int = 2,
        font_scale: float = 0.6,
    ):
        self.kp_thresh = keypoint_threshold
        self.kp_radius = keypoint_radius
        self.bone_thickness = bone_thickness
        self.bbox_thickness = bbox_thickness
        self.font_scale = font_scale

    def generate(
        self,
        video_path: str,
        output_path: str,
        frame_results: list[dict],
        action_events: list[dict],
        transcription: list[dict],
        progress_fn=None,
    ) -> str:
        """
        生成标注视频。

        Args:
            video_path: 原始视频路径
            output_path: 输出视频路径
            frame_results: 逐帧检测结果 [{timestamp, persons: [{bbox, keypoints, confidence}]}]
            action_events: 动作事件 [{time, action, confidence, actor_track_id}]
            transcription: 语音转写 [{start, end, text, speaker, speaker_role}]
            progress_fn: 进度回调 fn(done, total)

        Returns:
            输出视频的绝对路径
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        video_writer_fourcc = getattr(cv2, "VideoWriter_fourcc")
        fourcc = video_writer_fourcc(*"avc1")
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        if not writer.isOpened():
            cap.release()
            raise RuntimeError(f"无法创建输出视频: {output_path}")

        fr_timestamps = [fr["timestamp"] for fr in frame_results]
        action_timestamps = [ev["time"] for ev in action_events]
        trans_lookup = self._build_transcription_lookup(transcription)

        logger.info(
            f"开始生成标注视频: {total_frames}帧, "
            f"{len(frame_results)}个检测结果, "
            f"{len(action_events)}个动作事件, "
            f"{len(transcription)}段转写"
        )

        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / fps if fps > 0 else 0.0

            persons = self._find_nearest_detections(
                timestamp, fr_timestamps, frame_results
            )
            active_actions = self._find_active_actions(
                timestamp, action_timestamps, action_events
            )
            subtitle_text = self._find_subtitle(timestamp, trans_lookup)

            self._draw_persons(frame, persons)
            self._draw_action_labels(frame, active_actions, persons)
            self._draw_subtitle(frame, subtitle_text, width, height)
            self._draw_timestamp(frame, timestamp)

            writer.write(frame)
            frame_idx += 1

            if progress_fn and (frame_idx % 100 == 0 or frame_idx == total_frames):
                progress_fn(frame_idx, total_frames)

        cap.release()
        writer.release()

        abs_path = str(Path(output_path).resolve())
        logger.info(f"标注视频生成完成: {abs_path} ({frame_idx}帧)")
        return abs_path

    def _find_nearest_detections(
        self, timestamp: float, fr_timestamps: list[float], frame_results: list[dict]
    ) -> list[dict]:
        """通过二分查找定位最近的检测帧，容差 0.15s。"""
        if not fr_timestamps:
            return []
        idx = bisect.bisect_left(fr_timestamps, timestamp)
        best_idx = None
        best_diff = float("inf")
        for candidate in [idx - 1, idx]:
            if 0 <= candidate < len(fr_timestamps):
                diff = abs(fr_timestamps[candidate] - timestamp)
                if diff < best_diff:
                    best_diff = diff
                    best_idx = candidate
        if best_idx is not None and best_diff < 0.15:
            return frame_results[best_idx].get("persons", [])
        return []

    def _find_active_actions(
        self,
        timestamp: float,
        action_timestamps: list[float],
        action_events: list[dict],
    ) -> list[dict]:
        """找到 ±1.5s 窗口内的动作事件。"""
        if not action_timestamps:
            return []
        lo = bisect.bisect_left(action_timestamps, timestamp - 1.5)
        hi = bisect.bisect_right(action_timestamps, timestamp + 1.5)
        return action_events[lo:hi]

    @staticmethod
    def _build_transcription_lookup(transcription: list[dict]) -> list[dict]:
        """预处理转写数据，按 start 排序以便快速查找。"""
        sorted_trans = sorted(transcription, key=lambda s: s.get("start", 0.0))
        return sorted_trans

    def _find_subtitle(self, timestamp: float, sorted_trans: list[dict]) -> str:
        """查找当前时间点对应的语音字幕文本。"""
        parts = []
        for seg in sorted_trans:
            seg_start = seg.get("start", 0.0)
            seg_end = seg.get("end", seg_start)
            if seg_start > timestamp + 0.5:
                break
            if seg_start <= timestamp <= seg_end + 0.5:
                speaker = seg.get("speaker_role") or seg.get("speaker") or ""
                text = seg.get("text", "")
                if speaker and text:
                    parts.append(f"[{speaker}] {text}")
                elif text:
                    parts.append(text)
        return "  |  ".join(parts[-2:]) if parts else ""

    def _draw_persons(self, frame: np.ndarray, persons: list[dict]) -> None:
        """绘制每个人的边界框、骨架和关键点。"""
        for person in persons:
            bbox = person.get("bbox", [])
            kps = person.get("keypoints")
            conf = person.get("confidence", 0.0)

            if len(bbox) >= 4:
                x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
                cv2.rectangle(
                    frame, (x1, y1), (x2, y2), BBOX_COLOR, self.bbox_thickness
                )
                label = f"{conf:.0%}"
                cv2.putText(
                    frame,
                    label,
                    (x1, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    BBOX_COLOR,
                    1,
                    cv2.LINE_AA,
                )

            if kps is not None:
                kps_array = np.array(kps) if not isinstance(kps, np.ndarray) else kps
                if kps_array.ndim == 2 and kps_array.shape[0] >= 17:
                    self._draw_skeleton(frame, kps_array)
                    self._draw_keypoints(frame, kps_array)

    def _draw_skeleton(self, frame: np.ndarray, keypoints: np.ndarray) -> None:
        """绘制 COCO 17-keypoint 骨架连线。"""
        for i, j in SKELETON_CONNECTIONS:
            if keypoints[i][2] < self.kp_thresh or keypoints[j][2] < self.kp_thresh:
                continue
            pt1 = (int(keypoints[i][0]), int(keypoints[i][1]))
            pt2 = (int(keypoints[j][0]), int(keypoints[j][1]))
            color = BONE_COLORS.get((i, j), (128, 128, 128))
            cv2.line(frame, pt1, pt2, color, self.bone_thickness, cv2.LINE_AA)

    def _draw_keypoints(self, frame: np.ndarray, keypoints: np.ndarray) -> None:
        """绘制关键点圆圈。"""
        for k in range(keypoints.shape[0]):
            if keypoints[k][2] < self.kp_thresh:
                continue
            pt = (int(keypoints[k][0]), int(keypoints[k][1]))
            cv2.circle(frame, pt, self.kp_radius, KEYPOINT_COLOR, -1, cv2.LINE_AA)

    def _draw_action_labels(
        self, frame: np.ndarray, actions: list[dict], persons: list[dict]
    ) -> None:
        """在画面右上角区域绘制当前活跃的动作标签。"""
        if not actions:
            return

        # 去重: 同一动作只显示一次
        seen = set()
        unique_actions = []
        for act in actions:
            action_name = act.get("action", "unknown")
            if action_name not in seen:
                seen.add(action_name)
                unique_actions.append(act)

        h, w = frame.shape[:2]
        y_offset = 30
        for act in unique_actions:
            action_name = act.get("action", "unknown")
            confidence = act.get("confidence", 0.0)
            label_zh = ACTION_LABELS_ZH.get(action_name, action_name)
            color = ACTION_COLORS.get(action_name, (255, 255, 255))
            text = f"{label_zh} ({confidence:.0%})"

            # 半透明背景
            (tw, th), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, self.font_scale, 2
            )
            x_pos = w - tw - 15
            overlay = frame.copy()
            cv2.rectangle(
                overlay,
                (x_pos - 5, y_offset - th - 5),
                (x_pos + tw + 5, y_offset + 5),
                (0, 0, 0),
                -1,
            )
            cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

            cv2.putText(
                frame,
                text,
                (x_pos, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                self.font_scale,
                color,
                2,
                cv2.LINE_AA,
            )
            y_offset += th + 15

    def _draw_subtitle(
        self, frame: np.ndarray, text: str, width: int, height: int
    ) -> None:
        """在画面底部绘制语音字幕条。"""
        if not text:
            return

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = self.font_scale * 0.9
        thickness = 1
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)

        # 如果文本太长，截断
        max_w = int(width * 0.9)
        if tw > max_w:
            ratio = max_w / tw
            text = text[: int(len(text) * ratio)] + "..."
            (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)

        bar_h = th + 20
        bar_y = height - bar_h

        # 半透明黑色背景条
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, bar_y), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        x = (width - tw) // 2
        y = bar_y + (bar_h + th) // 2 - 2
        cv2.putText(
            frame, text, (x, y), font, scale, (255, 255, 255), thickness, cv2.LINE_AA
        )

    def _draw_timestamp(self, frame: np.ndarray, timestamp: float) -> None:
        """左上角显示当前时间戳。"""
        minutes = int(timestamp) // 60
        seconds = int(timestamp) % 60
        ms = int((timestamp % 1) * 100)
        text = f"{minutes:02d}:{seconds:02d}.{ms:02d}"
        cv2.putText(
            frame,
            text,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
