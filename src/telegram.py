"""Format the digest and send it to Telegram: one short card per paper."""

from __future__ import annotations

import html
from datetime import date

import requests

from .arxiv_client import Paper
from .summarizer import Explanation

TELEGRAM_LIMIT = 4096


def topic_emoji(paper: Paper) -> str:
    if any(c.startswith("q-fin") for c in paper.categories):
        return "📈"
    return "🤖"


def stars(score: int | None) -> str:
    if score is None:
        return ""
    return "★" * score + "☆" * (5 - score)


def format_paper(paper: Paper, exp: Explanation, index: int, total: int) -> str:
    e = html.escape
    authors = ", ".join(paper.authors[:2]) + (" et al." if len(paper.authors) > 2 else "")

    lines = [
        f"{topic_emoji(paper)} <b>{e(paper.title)}</b>",
        f"<i>{e(authors)}</i>",
        "",
        f"• <b>In short:</b> {e(exp.tldr)}",
    ]
    if exp.analogy:
        lines.append(f"• <b>Picture it:</b> {e(exp.analogy)}")
    if exp.why_it_matters:
        lines.append(f"• <b>Why it matters:</b> {e(exp.why_it_matters)}")
    if exp.score is not None:
        reason = f" — {e(exp.score_reason)}" if exp.score_reason else ""
        lines.append(f"• <b>Worth reading:</b> {stars(exp.score)}{reason}")
    lines += ["", f'<a href="{e(paper.url)}">Read the paper →</a>   <i>{index}/{total}</i>']

    return "\n".join(lines)[:TELEGRAM_LIMIT]


def build_messages(items: list[tuple[Paper, Explanation]], today: date) -> list[str]:
    """A short intro message, then one message per paper."""
    if not items:
        return [f"📚 <b>arXiv digest · {today:%a %d %b}</b>\n\nNo new relevant papers today."]

    # Best papers first, unscored ones last.
    items = sorted(items, key=lambda item: item[1].score or 0, reverse=True)
    total = len(items)
    noun = "paper" if total == 1 else "papers"
    intro = (
        f"📚 <b>arXiv digest · {today:%a %d %b}</b>\n"
        f"{total} new {noun} on finance &amp; foundation models, best first."
    )
    return [intro] + [format_paper(p, exp, i, total) for i, (p, exp) in enumerate(items, 1)]


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
