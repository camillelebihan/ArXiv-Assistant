"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_CATEGORIES = ["q-fin.ST", "q-fin.CP", "q-fin.PM", "q-fin.TR", "cs.LG"]
DEFAULT_KEYWORDS = [
    "finance",
    "financial",
    "stock",
    "portfolio",
    "trading",
    "asset pricing",
    "time series",
    "foundation model",
    "large language model",
    "llm",
]


def _split(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Config:
    telegram_token: str = ""
    telegram_chat_id: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    max_papers: int = 8
    lookback_hours: int = 36
    send_time: str = "08:00"
    timezone: str = "Europe/Paris"
    db_path: str = "/data/seen.db"

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            categories=_split(os.getenv("ARXIV_CATEGORIES"), DEFAULT_CATEGORIES),
            keywords=_split(os.getenv("KEYWORDS"), DEFAULT_KEYWORDS),
            max_papers=int(os.getenv("MAX_PAPERS", "8")),
            lookback_hours=int(os.getenv("LOOKBACK_HOURS", "36")),
            send_time=os.getenv("SEND_TIME", "08:00"),
            timezone=os.getenv("TZ_NAME", "Europe/Paris"),
            db_path=os.getenv("DB_PATH", "/data/seen.db"),
        )

    def missing(self) -> list[str]:
        """Names of required settings that are empty."""
        required = {
            "TELEGRAM_BOT_TOKEN": self.telegram_token,
            "TELEGRAM_CHAT_ID": self.telegram_chat_id,
            "GEMINI_API_KEY": self.gemini_api_key,
        }
        return [name for name, value in required.items() if not value]
