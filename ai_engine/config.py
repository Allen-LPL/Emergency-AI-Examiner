"""AI Engine configuration."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class AIEngineConfig(BaseSettings):
    """Configuration for the AI processing engine."""

    # Device
    device: str = Field(default="cuda:0", description="Compute device (cuda:0, cpu)")

    # Video Processing
    video_fps: int = Field(default=10, description="Target FPS for frame extraction")
    yolo_model: str = Field(default="yolov8n.pt", description="YOLO model path or name")
    yolo_conf_threshold: float = Field(
        default=0.3, description="YOLO confidence threshold"
    )
    yolo_iou_threshold: float = Field(default=0.5, description="YOLO NMS IoU threshold")
    tracker_type: str = Field(
        default="bytetrack.yaml", description="Tracker config file"
    )
    pose_model: str = Field(
        default="rtmpose-m",
        description="Pose estimation model name",
    )
    pose_keypoint_threshold: float = Field(
        default=0.3, description="Keypoint confidence threshold"
    )

    # Audio Processing
    asr_model: str = Field(
        default="iic/SenseVoiceSmall",
        description="FunASR model for Chinese ASR",
    )
    vad_model: str = Field(
        default="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        description="VAD model for speech detection",
    )
    sample_rate: int = Field(default=16000, description="Audio sample rate in Hz")
    hf_token: Optional[str] = Field(
        default=None, description="HuggingFace token for pyannote"
    )

    # Scoring
    max_speakers: int = Field(
        default=4, description="Maximum number of speakers to detect"
    )

    # Paths
    upload_dir: str = Field(default="./uploads", description="Upload directory")
    output_dir: str = Field(default="./outputs", description="Output directory")
    model_dir: str = Field(
        default="./ai_engine/models", description="Model weights directory"
    )

    model_config = {"env_prefix": "AI_", "env_file": ".env"}


def get_ai_config() -> AIEngineConfig:
    """Get AI engine configuration singleton."""
    return AIEngineConfig()
