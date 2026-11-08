"""Reader-friendly cards and the weekly big picture, written by Gemini."""

from __future__ import annotations

import logging

from .llm import Gemini, LLMError
from .ranker import Pick, describe

log = logging.getLogger("arxiv-digest")

CARD_FIELDS = (
    "in_short",
    "picture_it",
    "key_term",
    "why_it_matters",
    "future_signal",
    "ask",
)

CARD_PROMPT = """You explain a new research paper to an ambitious, non-specialist reader who wants
to talk confidently with AI founders and researchers. Plain English, no hype.
Every field is ONE sentence of at most 25 words.

Return JSON with exactly these keys:
- "in_short": what the paper does and finds.
- "picture_it": an everyday visual analogy for the core idea, starting with "Like".
- "key_term": one technical term from the paper and its meaning, as "Term: meaning".
- "why_it_matters": what this could change for companies, products or people.
- "future_signal": what this suggests about where AI or this field is heading.
- "ask": one sharp question the reader could ask a founder or researcher about this.

Title: {title}
Abstract: {abstract}
"""

WEEKLY_PROMPT = """Here are the most important AI papers of the week, as JSON:
{papers}

Write for an ambitious reader who wants to think strategically about the future of AI.
Return JSON with:
- "big_picture": a list of 3 short sentences (max 25 words each), each naming a trend
  you see across these papers and what it means for innovation.
- "watch_next": one sentence on what to keep an eye on next week.
"""


def fallback_card(pick: Pick) -> dict[str, str]:
    first = pick.abstract.split(". ")[0].strip().rstrip(".")
    return {"in_short": f"{first}." if first else pick.title}


def write_card(pick: Pick, llm: Gemini) -> dict[str, str]:
    try:
        data = llm.json(CARD_PROMPT.format(title=pick.title, abstract=pick.abstract))
    except LLMError as exc:
        log.error("Card for %s failed: %s", pick.arxiv_id, exc)
        return fallback_card(pick)
    if not isinstance(data, dict) or not data.get("in_short"):
        return fallback_card(pick)
    return {k: str(data[k]).strip() for k in CARD_FIELDS if data.get(k)}


def weekly_big_picture(picks: list[Pick], llm: Gemini) -> dict:
    if not picks:
        return {}
    try:
        data = llm.json(WEEKLY_PROMPT.format(papers=describe(picks)))
    except LLMError as exc:
        log.error("Weekly synthesis failed: %s", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    trends = data.get("big_picture") or []
    return {
        "big_picture": [str(t).strip() for t in trends if str(t).strip()][:3],
        "watch_next": str(data.get("watch_next", "")).strip(),
    }
