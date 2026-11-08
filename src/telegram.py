"""Format the digest and send it to Telegram."""

from __future__ import annotations

import html
from datetime import date

import requests

from .arxiv_client import Paper

TELEGRAM_LIMIT = 4096


def format_paper(paper: Paper, summary: str) -> str:
    authors = ", ".join(paper.authors[:3]) + (" et al." if len(paper.authors) > 3 else "")
    return (
        f'<b><a href="{html.escape(paper.url)}">{html.escape(paper.title)}</a></b>\n'
        f"<i>{html.escape(authors)}</i>\n"
        f"{html.escape(summary)}"
    )


def build_messages(items: list[tuple[Paper, str]], today: date) -> list[str]:
    """Split the digest into Telegram-sized messages."""
    header = f"📚 <b>arXiv digest, {today:%d %b %Y}</b> — {len(items)} papers\n\n"
    if not items:
        return [header + "No new relevant papers today."]

    messages, current = [], header
    for paper, summary in items:
        block = format_paper(paper, summary) + "\n\n"
        if len(current) + len(block) > TELEGRAM_LIMIT:
            messages.append(current.rstrip())
            current = ""
        current += block
    messages.append(current.rstrip())
    return messages


def send(token: str, chat_id: str, text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    response.raise_for_status()
