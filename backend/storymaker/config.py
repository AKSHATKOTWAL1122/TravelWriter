from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Backend settings.

    Lookup order: environment variable, then backend/.env, then the default.
    The app's own settings use the STORYMAKER_ prefix; third-party keys keep
    their standard names (via validation_alias, which skips the prefix).
    New settings go here and in backend/.env.example together.
    """

    model_config = SettingsConfigDict(
        env_prefix="STORYMAKER_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Only LLM calls need the key, so the app must start without it.
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    model: str = "gemini-2.5-flash"


@lru_cache
def get_settings() -> Settings:
    return Settings()
