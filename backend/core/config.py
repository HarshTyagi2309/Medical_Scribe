from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Medical Scribe API"
    app_version: str = "2.4.0"

    environment: str = field(
        default_factory=lambda: os.getenv(
            "APP_ENV",
            "development",
        ).strip().lower()
    )

    log_level: str = field(
        default_factory=lambda: os.getenv(
            "LOG_LEVEL",
            "INFO",
        ).strip().upper()
    )

    timezone: str = field(
        default_factory=lambda: os.getenv(
            "APP_TIMEZONE",
            "Asia/Kolkata",
        ).strip()
    )

    max_audio_size_mb: int = field(
        default_factory=lambda: int(
            os.getenv(
                "MAX_AUDIO_SIZE_MB",
                "25",
            )
        )
    )

    allowed_audio_extensions: tuple[str, ...] = (
        ".wav",
        ".mp3",
        ".m4a",
        ".ogg",
        ".webm",
    )

    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in os.getenv(
                "ALLOWED_ORIGINS",
                "http://localhost:8501,http://127.0.0.1:8501",
            ).split(",")
            if origin.strip()
        )
    )

    langfuse_public_key: str = field(
        default_factory=lambda: os.getenv(
            "LANGFUSE_PUBLIC_KEY",
            "",
        ).strip(),
        repr=False,
    )

    langfuse_secret_key: str = field(
        default_factory=lambda: os.getenv(
            "LANGFUSE_SECRET_KEY",
            "",
        ).strip(),
        repr=False,
    )

    storage_dir: str = field(
        default_factory=lambda: os.getenv(
            "STORAGE_DIR",
            "",
        ).strip()
    )

    groq_api_key: str = field(
        default_factory=lambda: os.getenv(
            "GROQ_API_KEY",
            "",
        ).strip(),
        repr=False,
    )

    openai_api_key: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_API_KEY",
            "",
        ).strip(),
        repr=False,
    )

    jwt_secret_key: str = field(
        default_factory=lambda: os.getenv(
            "JWT_SECRET_KEY",
            "",
        ).strip(),
        repr=False,
    )

    data_encryption_key: str = field(
        default_factory=lambda: os.getenv(
            "DATA_ENCRYPTION_KEY",
            "",
        ).strip(),
        repr=False,
    )

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def storage_root(self) -> Path:
        if self.storage_dir:
            return Path(
                self.storage_dir
            ).expanduser().resolve()

        return self.project_root

    @property
    def recordings_dir(self) -> Path:
        return self.storage_root / "recordings"

    @property
    def logs_dir(self) -> Path:
        return self.storage_root / "logs"

    @property
    def max_audio_size_bytes(self) -> int:
        return self.max_audio_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment in {
            "production",
            "prod",
        }

    def ensure_runtime_directories(self) -> None:
        self.recordings_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.logs_dir.mkdir(
            parents=True,
            exist_ok=True,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_directories()
    return settings
