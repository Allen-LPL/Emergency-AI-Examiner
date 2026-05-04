from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "emergency_examiner"
    postgres_user: str = "postgres"
    postgres_password: str = "changeme"

    redis_host: str = "localhost"
    redis_port: int = 6379

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    secret_key: str = "changeme-to-a-random-secret-key"
    access_token_expire_minutes: int = 1440
    algorithm: str = "HS256"

    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    max_upload_size_mb: int = 2048

    debug: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    ai_device: str = "cpu"
    video_fps: int = 10
    asr_model: str = "iic/SenseVoiceSmall"
    pose_model: str = "rtmpose-m"
    yolo_model: str = "yolov8n.pt"
    hf_token: str = ""

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
