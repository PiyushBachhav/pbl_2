"""
Application configuration loaded from environment variables / .env file.

All secrets (DATABASE_URL, SECRET_KEY, etc.) come from the environment.
Never hard-code them here.
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://visionsafe:visionsafe@localhost:5432/visionsafe",
        description="Async PostgreSQL connection string (asyncpg driver).",
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql://visionsafe:visionsafe@localhost:5432/visionsafe",
        description="Sync PostgreSQL connection string (for Alembic).",
    )

    # --- Application ---
    SECRET_KEY: str = Field(default="dev-secret-change-in-production")
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    LOG_LEVEL: str = Field(default="INFO")
    FRONTEND_URL: str = Field(default="http://localhost:5173")

    # --- ML / Vision ---
    MODEL_PATH: str = Field(default="models/yolov8n.pt")
    DEVICE: str = Field(
        default="cpu",
        description="Inference device: 'cuda', 'cpu', or '0' for CUDA device index.",
    )
    CONFIDENCE: float = Field(default=0.35, ge=0.0, le=1.0)
    IOU: float = Field(default=0.5, ge=0.0, le=1.0)

    # --- Paths ---
    EVIDENCE_DIR: str = Field(default="evidence")
    VIDEO_DIR: str = Field(default="videos")
    MODELS_DIR: str = Field(default="models")

    # --- Processing ---
    FRAME_SKIP: int = Field(default=1, ge=1, description="Process every Nth frame.")
    MAX_CONCURRENT_JOBS: int = Field(default=2)

    @property
    def evidence_path(self) -> Path:
        p = Path(self.EVIDENCE_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def video_path(self) -> Path:
        p = Path(self.VIDEO_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def models_path(self) -> Path:
        return Path(self.MODELS_DIR)


settings = Settings()
