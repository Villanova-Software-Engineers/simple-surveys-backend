"""Application configuration settings."""

from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment and defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    allowed_origins: List[str] = ["*"]

    # Storage settings
    storage_backend: str = "file_storage"  # "file_storage", "firebase", or "ms_graph"
    data_dir: Path = Path("data")

    # Firebase / Google Cloud settings
    firebase_credentials_path: Optional[str] = None
    firebase_credentials_json: Optional[str] = None
    firebase_project_id: Optional[str] = None
    firebase_storage_bucket: Optional[str] = None
    firestore_database: Optional[str] = None

    # Survey response expiration
    time_to_complete_minutes: int = 5

    # Notification / Scheduler settings
    scheduler_timezone: str = "America/New_York"

    @property
    def surveys_dir(self) -> Path:
        """Directory holding survey definition JSON files."""
        return self.data_dir / "surveys"

    @property
    def schedule_config_dir(self) -> Path:
        """Directory holding notification and sampling rules."""
        return self.data_dir / "schedule_config"

    @property
    def responses_dir(self) -> Path:
        """Directory holding organized response records and images."""
        return self.data_dir / "responses"

    @property
    def devices_dir(self) -> Path:
        """Directory holding device registration tokens."""
        return self.data_dir / "devices"

    @property
    def sampling_rules_path(self) -> Path:
        """Path to sampling rules JSON file."""
        return self.schedule_config_dir / "sampling_rules.json"

    @property
    def image_cache_dir(self) -> Path:
        """Directory holding cached images downloaded from cloud storage."""
        return self.data_dir / "cache" / "images"


settings = Settings()
