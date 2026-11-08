"""Reader-friendly cards and the weekly big picture, written by Gemini."""

from __future__ import annotations

import logging

from .llm import Gemini, LLMError
from .ranker import Pick, as_index, describe

log = logging.getLogger("arxiv-digest")

CARD_FIELDS = (
    "in_short",
    "picture_it",
    "key_term",
    "why_it_matters",
    "future_signal",
    "ask",
)

CARDS_PROMPT = """You explain new research papers to an ambitious, non-specialist reader who wants
to talk confidently with AI founders and researchers. Plain English, no hype.
Every field is ONE sentence of at most 25 words.

For EACH paper below, return an object with exactly these keys:
- "i": the paper's number.
- "in_short": what the paper does and finds.
- "picture_it": an everyday visual analogy for the core idea, starting with "Like".
- "key_term": one technical term from the paper and its meaning, as "Term: meaning".
- "why_it_matters": what this could change for companies, products or people.
- "future_signal": what this suggests about where AI or this field is heading.
- "ask": one sharp question the reader could ask a founder or researcher about this.

Return a JSON list of these objects, one per paper.

Papers:
{papers}
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


def parse_cards(data: object, picks: list[Pick]) -> list[dict[str, str] | None]:
    """Match Gemini's list back to the picks; None where a card is missing."""
    if isinstance(data, dict):  # some models wrap the list in an object
        data = next((v for v in data.values() if isinstance(v, list)), [])
    cards: dict[int, dict[str, str]] = {}
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict) or not row.get("in_short"):
            continue
        i = as_index(row.get("i"))
        if i is not None and 0 <= i < len(picks):
            cards[i] = {k: str(row[k]).strip() for k in CARD_FIELDS if row.get(k)}
    return [cards.get(i) for i in range(len(picks))]


def _ask(picks: list[Pick], llm: Gemini) -> list[dict[str, str] | None]:
    listing = "\n\n".join(f"[{i}] {p.title}\n{p.abstract}" for i, p in enumerate(picks))
    try:
        return parse_cards(llm.json(CARDS_PROMPT.format(papers=listing)), picks)
    except LLMError as exc:
        log.error("Writing cards failed: %s", exc)
        return [None] * len(picks)


def write_cards(picks: list[Pick], llm: Gemini) -> list[dict[str, str]]:
    """All cards in one Gemini call, plus one follow-up call for any card it skipped."""
    if not picks:
        return []
    cards = _ask(picks, llm)
    missing = [i for i, card in enumerate(cards) if card is None]
    if missing:
        log.info("Retrying %d missing card(s)", len(missing))
        for i, card in zip(missing, _ask([picks[i] for i in missing], llm), strict=True):
            cards[i] = card
    return [card or fallback_card(p) for card, p in zip(cards, picks, strict=True)]


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
