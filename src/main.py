"""Command-line entry point.

    python -m src.main check            test Gemini and Telegram, print what is wrong
    python -m src.main daily            build and send today's digest now
    python -m src.main weekly           build and send this week's digest now
    python -m src.main auto [--site D]  send whatever is due (used by the schedule)
    python -m src.main site D           only rebuild the website into folder D
    python -m src.main loop             run `auto` every 20 minutes (local Docker)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import telegram
from .arxiv_client import fetch_recent, preselect
from .config import Config
from .llm import Gemini, LLMError
from .ranker import score_papers, select_diverse
from .site import build_site
from .state import State
from .summarizer import weekly_big_picture, write_cards
from .topics import load_topics

log = logging.getLogger("arxiv-digest")


# --- scheduling ------------------------------------------------------------
def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_label(sunday: date) -> str:
    monday = sunday - timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday:%-d %b %Y}"
    return f"{monday:%-d %b}–{sunday:%-d %b %Y}"


def due_jobs(now: datetime, meta: dict, daily_hour: int, weekly_hour: int) -> list[str]:
    """Which digests are due at local time `now`, given what was already sent."""
    jobs: list[str] = []
    today = now.date()
    if now.weekday() < 5 and now.hour >= daily_hour and meta.get("last_daily") != str(today):
        jobs.append("daily")
    if now.weekday() == 6 and now.hour >= weekly_hour and meta.get("last_weekly") != week_key(
        today
    ):
        jobs.append("weekly")
    return jobs


# --- jobs ------------------------------------------------------------------
def run_daily(cfg: Config, state: State, llm: Gemini, today: date) -> int:
    topics = load_topics(cfg.topics_path)
    seen = state.seen_ids()
    papers = [p for p in fetch_recent(topics, cfg.lookback_hours) if p.arxiv_id not in seen]
    candidates = preselect(papers, topics, cfg.candidates)
    log.info("%d new papers, %d match your themes", len(papers), len(candidates))

    scored = score_papers(candidates, topics, llm)
    if candidates and not scored:
        # Gemini is down or out of quota: send nothing and keep the papers for the next run.
        raise LLMError("no paper could be scored; nothing sent, will retry on the next run")
    picks = select_diverse(scored, cfg.daily_count)
    for pick, card in zip(picks, write_cards(picks, llm), strict=True):
        pick.card = card
        pick.date = today.isoformat()

    day_url = f"{cfg.site_url.rstrip('/')}/days/{today}.html" if cfg.site_url else ""
    for message in telegram.daily_messages(picks, today, day_url):
        telegram.send(cfg.telegram_token, cfg.telegram_chat_id, message)

    state.save_day(today, picks)
    state.mark_seen([p.arxiv_id for p in candidates], today)
    state.set_meta(last_daily=today.isoformat())
    return len(picks)


def run_weekly(cfg: Config, state: State, llm: Gemini, today: date) -> int:
    sunday = today + timedelta(days=(6 - today.weekday()))
    if sunday > today:  # run mid-week: summarise the week so far
        sunday = today
    pool = {p.arxiv_id: p for p in state.picks_between(sunday - timedelta(days=6), sunday)}
    picks = sorted(pool.values(), key=lambda p: p.overall, reverse=True)[: cfg.weekly_count]
    synthesis = weekly_big_picture(picks, llm)

    key, label = week_key(sunday), week_label(sunday)
    week_url = f"{cfg.site_url.rstrip('/')}/weeks/{key}.html" if cfg.site_url else ""
    for message in telegram.weekly_messages(picks, synthesis, label, week_url):
        telegram.send(cfg.telegram_token, cfg.telegram_chat_id, message)

    state.save_week(key, label, synthesis, picks)
    state.set_meta(last_weekly=key)
    return len(picks)


def run_check(cfg: Config) -> bool:
    ok = True
    print(f"Gemini model: {cfg.gemini_model}")
    try:
        Gemini(cfg.gemini_api_key, cfg.gemini_model, min_interval=0, retries=1).json(
            'Reply with the JSON object {"ok": true}.'
        )
        print("✅ Gemini works")
    except LLMError as exc:
        ok = False
        print(f"❌ Gemini failed: {exc}")
    try:
        telegram.send(cfg.telegram_token, cfg.telegram_chat_id, "✅ Test from your arXiv bot")
        print("✅ Telegram works (check your chat)")
    except Exception as exc:
        ok = False
        print(f"❌ Telegram failed: {exc}")
    return ok


# --- entry point -------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Daily AI research digest on Telegram")
    parser.add_argument("command", choices=["check", "daily", "weekly", "auto", "site", "loop"])
    parser.add_argument("site_dir", nargs="?", help="output folder for `site`")
    parser.add_argument("--site", dest="site_out", help="also rebuild the website here")
    args = parser.parse_args(argv)

    cfg = Config.from_env()
    state = State(cfg.data_dir)
    tz = ZoneInfo(cfg.timezone)

    if args.command == "site":
        build_site(state, args.site_dir or "_site")
        return

    if missing := cfg.missing():
        log.error("Missing environment variables: %s", ", ".join(missing))
        sys.exit(1)

    if args.command == "check":
        sys.exit(0 if run_check(cfg) else 1)

    llm = Gemini(cfg.gemini_api_key, cfg.gemini_model, cfg.gemini_interval)

    def run(jobs: list[str]) -> None:
        today = datetime.now(tz).date()
        for job in jobs:
            log.info("Running %s digest", job)
            if job == "daily":
                run_daily(cfg, state, llm, today)
            else:
                run_weekly(cfg, state, llm, today)
        if args.site_out:
            build_site(state, args.site_out)

    if args.command in ("daily", "weekly"):
        run([args.command])
    elif args.command == "auto":
        run(due_jobs(datetime.now(tz), state.meta, cfg.daily_hour, cfg.weekly_hour))
    else:  # loop
        while True:
            try:
                run(due_jobs(datetime.now(tz), state.meta, cfg.daily_hour, cfg.weekly_hour))
            except Exception:  # keep the loop alive; the error is logged
                log.exception("Run failed")
            time.sleep(20 * 60)


if __name__ == "__main__":
    main()
