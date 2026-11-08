"""Entry point: run the digest once, or every day at SEND_TIME."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import telegram
from .arxiv_client import fetch_recent
from .config import Config
from .storage import SeenStore
from .summarizer import Summarizer

log = logging.getLogger("arxiv-digest")


def run_digest(cfg: Config) -> int:
    store = SeenStore(cfg.db_path)
    papers = fetch_recent(cfg.categories, cfg.keywords, cfg.lookback_hours)
    new = [p for p in papers if not store.is_seen(p.arxiv_id)][: cfg.max_papers]
    log.info("Fetched %d relevant papers, %d new", len(papers), len(new))

    summarizer = Summarizer(cfg.gemini_api_key, cfg.gemini_model)
    items = [(p, summarizer.summarize(p)) for p in new]

    today = datetime.now(ZoneInfo(cfg.timezone)).date()
    for message in telegram.build_messages(items, today):
        telegram.send(cfg.telegram_token, cfg.telegram_chat_id, message)

    store.mark_seen([p.arxiv_id for p in new])
    return len(new)


def seconds_until(send_time: str, tz: str, now: datetime | None = None) -> float:
    zone = ZoneInfo(tz)
    now = now or datetime.now(zone)
    hour, minute = (int(x) for x in send_time.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Daily arXiv digest on Telegram")
    parser.add_argument("--once", action="store_true", help="send one digest now and exit")
    args = parser.parse_args()

    cfg = Config.from_env()
    if missing := cfg.missing():
        log.error("Missing environment variables: %s", ", ".join(missing))
        sys.exit(1)

    if args.once:
        run_digest(cfg)
        return

    while True:
        wait = seconds_until(cfg.send_time, cfg.timezone)
        log.info("Next digest in %.1f hours", wait / 3600)
        time.sleep(wait)
        try:
            run_digest(cfg)
        except Exception:
            log.exception("Digest failed; will retry tomorrow")


if __name__ == "__main__":
    main()
