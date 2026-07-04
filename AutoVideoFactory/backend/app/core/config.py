from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DatabaseProvider(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class StorageProvider(str, Enum):
    LOCAL = "local"
    GCS = "gcs"


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class VideoPlatform(str, Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"


class AIProviderType(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AVF_",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AutoVideoFactory"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True

    # Paths
    project_root: Path = Field(default_factory=lambda: Path(os.getcwd()).parent)
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")
    temp_dir: Path = Path("temp")
    logs_dir: Path = Path("logs")
    sessions_dir: Path = Path("sessions")
    assets_dir: Path = Path("assets")
    plugins_dir: Path = Path("plugins")

    # Server
    host: str = "127.0.0.1"
    port: int = 8080
    workers: int = 1
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Database
    database_provider: DatabaseProvider = DatabaseProvider.SQLITE
    database_url: Optional[str] = None
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_database_url(cls, v: Optional[str], info: Any) -> str:
        if v:
            return v
        data_dir = info.data.get("data_dir", Path("data"))
        return f"sqlite+aiosqlite:///{data_dir}/autovideofactory.db"

    # Authentication
    auth_enabled: bool = False
    auth_jwt_secret: str = "change-me-in-production"
    auth_jwt_algorithm: str = "HS256"
    auth_jwt_expire_minutes: int = 1440

    # Logging
    log_level: LogLevel = LogLevel.DEBUG
    log_format: str = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
    log_to_file: bool = True
    log_max_bytes: int = 10485760
    log_backup_count: int = 5

    # Browser
    browser_type: BrowserType = BrowserType.CHROMIUM
    browser_headless: bool = False
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 720
    browser_timeout: int = 30000
    browser_navigation_timeout: int = 60000
    browser_session_ttl_minutes: int = 120
    browser_max_sessions: int = 10
    browser_cdp_endpoint: Optional[str] = None
    browser_executable_path: Optional[str] = None

    # Browser Use (Computer Use Agent)
    browser_use_llm_provider: AIProviderType = AIProviderType.OLLAMA
    browser_use_llm_model: str = "llama3.2:3b"
    browser_use_max_actions: int = 100
    browser_use_use_vision: bool = True
    browser_use_save_traces: bool = True

    # Computer Vision / OCR
    ocr_enabled: bool = True
    ocr_confidence_threshold: float = 0.7
    cv_enable_loading_detection: bool = True
    cv_template_matching_threshold: float = 0.8

    # AI / LLM
    llm_provider: AIProviderType = AIProviderType.OLLAMA
    llm_model: str = "qwen2.5:32b"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None

    # OpenAI / API-based providers
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_default_model: str = "gpt-4o"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "qwen2.5:32b"

    # Content Generation
    default_video_width: int = 1080
    default_video_height: int = 1920
    default_video_fps: int = 30
    default_video_duration_seconds: int = 60
    max_video_duration_seconds: int = 300

    # Voice
    default_voice_provider: str = "edge-tts"
    default_voice_language: str = "en"
    voice_cloning_enabled: bool = False

    # Music
    music_library_path: Optional[str] = None
    royalty_free_music_enabled: bool = True

    # Storage
    storage_provider: StorageProvider = StorageProvider.LOCAL
    gcs_bucket_name: Optional[str] = None

    # Google / YouTube OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_client_id_2: Optional[str] = None
    google_client_secret_2: Optional[str] = None
    google_redirect_uri: str = "http://127.0.0.1:8080/api/v1/auth/youtube/callback"
    google_youtube_quota_per_account: int = 10000
    google_youtube_upload_cost: int = 1600

    # Instagram
    instagram_username: Optional[str] = None
    instagram_password: Optional[str] = None
    instagram_session_dir: str = "sessions/instagram"

    # Pixabay
    pixabay_api_key: Optional[str] = None

    # Publishing
    publisher_upload_interval_seconds: int = 30
    publisher_max_retries: int = 3
    publisher_retry_delay_seconds: int = 60

    # Analytics
    analytics_enabled: bool = True
    analytics_track_user_actions: bool = True

    # Learning Engine
    learning_enabled: bool = True
    learning_feedback_loop_interval: int = 3600

    # Queue / Scheduler
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 300
    max_concurrent_jobs: int = 2

    # Plugin System
    plugins_enabled: bool = True
    plugins_auto_discover: bool = True

    # Docker / Container
    container_mode: bool = False

    def model_post_init(self, __context: Any) -> None:
        for path_attr in [
            "data_dir",
            "output_dir",
            "temp_dir",
            "logs_dir",
            "sessions_dir",
            "assets_dir",
            "plugins_dir",
        ]:
            path: Path = getattr(self, path_attr)
            if not path.is_absolute():
                resolved = self.project_root / path
                object.__setattr__(self, path_attr, resolved)
            path = getattr(self, path_attr)
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
