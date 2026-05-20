# pyright: reportMissingImports=false
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
    max_total_frames: int = Field(
        default=600, description="Max frames to sample from video"
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

    # External ASR services
    funasr_ws_url: str = Field(
        default="ws://172.17.0.1:10095",
        description="FunASR WebSocket server URL (offline mode)",
    )
    # 超时从 120 提到 600 秒, 适配 5+ 分钟考核音频
    funasr_ws_timeout: int = Field(
        default=600, description="FunASR WebSocket 超时秒数 (含连接 + 转写)",
    )
    whisper_http_url: str = Field(
        default="http://172.28.0.1:9000/asr",
        description="Whisper ASR HTTP API endpoint",
    )
    whisper_http_timeout: int = Field(
        default=600, description="Whisper HTTP 请求超时秒数",
    )
    enable_external_asr: bool = Field(
        default=True,
        description="启用外部 ASR (FunASR WS + Whisper HTTP) 总开关",
    )

    # Tencent Cloud ASR (录音文件识别, 异步任务接口) — 与 FunASR/Whisper 解耦的第三路冗余
    enable_tencent_asr: bool = Field(
        default=False, description="是否启用腾讯云 ASR 第三路 (默认关闭)"
    )
    tencent_secret_id: str = Field(default="", description="腾讯云 SecretId")
    tencent_secret_key: str = Field(default="", description="腾讯云 SecretKey")
    tencent_app_id: int = Field(default=0, description="腾讯云 AppId")
    tencent_engine_type: str = Field(
        default="16k_zh", description="腾讯云 ASR 引擎模型, 默认 16k 中文通用"
    )
    tencent_asr_timeout: int = Field(
        default=600, description="腾讯云 ASR 总超时 (含轮询任务状态)"
    )

    # 路径相关:
    #   upload_dir / output_dir 默认相对路径, 由调用方在使用前通过 Path(...).resolve()
    #   转为绝对路径, 以适配 docker 多容器场景 (api 与 celery_worker 是两个容器,
    #   工作目录可能不同, 但通过宿主机绑定挂载共享 ./uploads 与 ./outputs).
    upload_dir: str = Field(default="./uploads", description="原始视频上传目录")
    output_dir: str = Field(
        default="./outputs",
        description="AI 标注视频输出目录 (含姿态骨架、关键点、动作标签、语音字幕)",
    )
    model_dir: str = Field(
        default="./ai_engine/models", description="模型权重目录"
    )

    model_config = {
        "env_prefix": "AI_",
        "env_file": ".env",
        "extra": "ignore",
        "protected_namespaces": ("settings_",),
    }


def get_ai_config() -> AIEngineConfig:
    """Get AI engine configuration singleton."""
    return AIEngineConfig()
