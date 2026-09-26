"""Application configuration and environment settings."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    # Base paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR: Path = BASE_DIR / "configs"
    OUTPUT_DIR: Path = BASE_DIR / "output"
    ASSETS_DIR: Path = BASE_DIR / "assets"

    # LLM Settings
    LLM_PROVIDER: str = "anthropic"  # 'anthropic' or 'google'
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    # Voice / ElevenLabs Settings
    ELEVENLABS_API_KEY: str = ""

    # LipSync / Avatar Settings
    HEDRA_API_KEY: str = ""
    HEYGEN_API_KEY: str = ""

    # LinkedIn Distribution
    LINKEDIN_ACCESS_TOKEN: str = ""
    LINKEDIN_AUTHOR_URN: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def init_directories(self) -> None:
        """Ensure runtime directories exist."""
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        (self.ASSETS_DIR / "personas").mkdir(parents=True, exist_ok=True)
        (self.ASSETS_DIR / "screencasts").mkdir(parents=True, exist_ok=True)


settings = AppSettings()
