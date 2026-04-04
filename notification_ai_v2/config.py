from __future__ import annotations

from dataclasses import dataclass
import os

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_api_url: str
    database_path: str
    default_delay_minutes: int
    request_timeout_seconds: int


def load_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv()

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_api_url = os.getenv(
        "GEMINI_API_URL",
        "https://generativelanguage.googleapis.com/v1beta/models",
    )

    database_path = os.getenv("NOTIF_DB_PATH", "./data/notification_ai_v2.db")
    default_delay_minutes = int(os.getenv("DEFAULT_DELAY_MINUTES", "15"))
    request_timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", "15"))

    return Settings(
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        gemini_api_url=gemini_api_url,
        database_path=database_path,
        default_delay_minutes=default_delay_minutes,
        request_timeout_seconds=request_timeout_seconds,
    )
