"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass
class Config:
    telegram_token: str = ""
    telegram_chat_id: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_interval: float = 4.0
    topics_path: str = "topics.toml"
    data_dir: str = "/data"
    site_url: str = ""
    timezone: str = "Europe/Paris"
    daily_hour: int = 7
    weekly_hour: int = 9
    daily_count: int = 7
    weekly_count: int = 5
    candidates: int = 60
    lookback_hours: int = 96

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
            gemini_interval=float(os.getenv("GEMINI_INTERVAL", "4")),
            topics_path=os.getenv("TOPICS_PATH", "topics.toml"),
            data_dir=os.getenv("DATA_DIR", "/data"),
            site_url=os.getenv("SITE_URL", ""),
            timezone=os.getenv("TZ_NAME", "Europe/Paris"),
            daily_hour=_int("DAILY_HOUR", 7),
            weekly_hour=_int("WEEKLY_HOUR", 9),
            daily_count=_int("DAILY_COUNT", 7),
            weekly_count=_int("WEEKLY_COUNT", 5),
            candidates=_int("CANDIDATES", 60),
            lookback_hours=_int("LOOKBACK_HOURS", 96),
        )

    def missing(self) -> list[str]:
        """Names of required settings that are empty."""
        required = {
            "TELEGRAM_BOT_TOKEN": self.telegram_token,
            "TELEGRAM_CHAT_ID": self.telegram_chat_id,
            "GEMINI_API_KEY": self.gemini_api_key,
        }
        return [name for name, value in required.items() if not value]
