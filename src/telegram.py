"""Telegram formatting and sending: one short card per paper."""

from __future__ import annotations

import html
from datetime import date

import requests

from .ranker import Pick

TELEGRAM_LIMIT = 4096
e = html.escape

LABELS = {
    "in_short": "In short",
    "picture_it": "Picture it",
    "key_term": "Key term",
    "why_it_matters": "Why it matters",
    "future_signal": "Future signal",
    "ask": "Ask an expert",
}
SCORE_LABELS = {"novelty": "Novelty", "rigor": "Rigor", "impact": "Impact", "relevance": "For you"}


def authors_line(authors: list[str]) -> str:
    return ", ".join(authors[:2]) + (" et al." if len(authors) > 2 else "")


def dots(score: int) -> str:
    return "●" * score + "○" * (5 - score)


def score_block(pick: Pick) -> str:
    rows = [f"{SCORE_LABELS[a]:<8} {dots(pick.scores.get(a, 1))}" for a in SCORE_LABELS]
    return f"<code>{e(chr(10).join(rows))}</code>\n<b>Overall {pick.overall:.1f}/5</b>"


def format_card(pick: Pick, index: int, total: int) -> str:
    lines = [
        f"{pick.emoji} <b>{e(pick.title)}</b>",
        f"<i>{e(authors_line(pick.authors))} · {e(pick.theme)}</i>",
        "",
    ]
    lines += [f"• <b>{label}:</b> {e(pick.card[key])}"
              for key, label in LABELS.items() if pick.card.get(key)]
    lines += ["", score_block(pick), "",
              f'<a href="{e(pick.url)}">Read the paper →</a>   <i>{index}/{total}</i>']
    return "\n".join(lines)[:TELEGRAM_LIMIT]


def daily_messages(picks: list[Pick], today: date, site_url: str = "") -> list[str]:
    title = f"☀️ <b>Your AI briefing · {today:%a %d %b}</b>"
    if not picks:
        return [f"{title}\n\nNo strong new papers today. Back tomorrow."]
    themes = " ".join(dict.fromkeys(p.emoji for p in picks))
    noun = "paper" if len(picks) == 1 else "papers"
    intro = f"{title}\n{len(picks)} {noun} worth your time, best first  {themes}"
    if site_url:
        intro += f'\n<a href="{e(site_url)}">Open on the web</a>'
    total = len(picks)
    return [intro] + [format_card(p, i, total) for i, p in enumerate(picks, 1)]


def weekly_messages(
    picks: list[Pick], synthesis: dict, week_label: str, site_url: str = ""
) -> list[str]:
    header = f"🗓️ <b>Your week in AI · {e(week_label)}</b>"
    if not picks:
        return [f"{header}\n\nNo papers were selected this week."]

    parts = [header, ""]
    if synthesis.get("big_picture"):
        parts.append("<b>The big picture</b>")
        parts += [f"• {e(t)}" for t in synthesis["big_picture"]]
        parts.append("")
    if synthesis.get("watch_next"):
        parts += [f"👀 <b>Watch next:</b> {e(synthesis['watch_next'])}", ""]
    parts.append(f"<b>Top {len(picks)} of the week</b>")
    for i, p in enumerate(picks, 1):
        summary = p.card.get("in_short", "")
        parts.append(
            f'{i}. {p.emoji} <a href="{e(p.url)}">{e(p.title)}</a> — {p.overall:.1f}/5\n'
            f"   {e(summary)}"
        )
    if site_url:
        parts += ["", f'<a href="{e(site_url)}">Read the full week on the web</a>']
    return [chunk for chunk in _split("\n".join(parts))]


def _split(text: str) -> list[str]:
    """Split on line breaks so no message exceeds Telegram's limit."""
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > TELEGRAM_LIMIT:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"
    chunks.append(current.rstrip())
    return chunks


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
    if not response.ok:
        # Telegram explains the problem in the body (bad token, chat not found...).
        raise RuntimeError(f"Telegram error {response.status_code}: {response.text[:300]}")
