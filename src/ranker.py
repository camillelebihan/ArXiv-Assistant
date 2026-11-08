"""Score candidate papers on four axes with Gemini, then pick a diverse top N."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from .arxiv_client import Paper
from .llm import Gemini, LLMError
from .topics import Topics

log = logging.getLogger("arxiv-digest")

AXES = ("novelty", "rigor", "impact", "relevance")

SCORING_PROMPT = """You are a sharp research scout. Score each paper from its title and abstract.

Reader profile: {profile}

Themes (pick the single best fit for each paper, using the exact name):
{themes}

Score each axis from 1 (low) to 5 (high), comparing the papers AGAINST EACH OTHER.
Use the whole scale. For each axis, across this batch aim for roughly:
10% get 5, 20% get 4, 40% get 3, 20% get 2, 10% get 1.
A 5 means "one of the best papers of the month", 3 means "solid but ordinary".
- novelty: genuinely new idea or result, not an incremental tweak.
- rigor: convincing evidence (strong baselines, real data, clear evaluation).
  Abstracts without concrete results or comparisons score at most 3.
- impact: could change products, industries, science or society.
- relevance: how useful this is for the reader profile above.

Return a JSON list, one object per paper:
[{{"i": 0, "theme": "<theme name>", "novelty": 3, "rigor": 3, "impact": 3, "relevance": 3}}]

Papers:
{papers}
"""


@dataclass
class Pick:
    arxiv_id: str
    title: str
    url: str
    authors: list[str]
    abstract: str
    theme: str
    emoji: str
    scores: dict[str, int]
    overall: float
    card: dict[str, str] = field(default_factory=dict)
    date: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Pick:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def as_index(value: object) -> int | None:
    """Gemini sometimes sends the paper number as a string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _clamp(value: object) -> int:
    try:
        return max(1, min(5, int(value)))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 1


def build_prompt(papers: list[Paper], topics: Topics) -> str:
    themes = "\n".join(f"- {t.name}: {t.description}" for t in topics.themes)
    listing = "\n\n".join(
        f"[{i}] {p.title}\n{p.abstract[:1200]}" for i, p in enumerate(papers)
    )
    return SCORING_PROMPT.format(profile=topics.profile, themes=themes, papers=listing)


def parse_scores(data: object, papers: list[Paper], topics: Topics) -> list[Pick]:
    """Turn Gemini's list into Picks, ignoring malformed rows."""
    if isinstance(data, dict):  # some models wrap the list in an object
        data = next((v for v in data.values() if isinstance(v, list)), [])
    if not isinstance(data, list):
        return []

    picks: list[Pick] = []
    seen: set[int] = set()
    for row in data:
        if not isinstance(row, dict):
            continue
        i = as_index(row.get("i"))
        if i is None or not 0 <= i < len(papers) or i in seen:
            continue
        seen.add(i)
        paper = papers[i]
        theme = topics.theme(str(row.get("theme", ""))) or topics.theme(
            paper.themes[0] if paper.themes else ""
        )
        if theme is None:
            continue
        scores = {axis: _clamp(row.get(axis)) for axis in AXES}
        # Theme weight nudges relevance (e.g. finance stays occasional).
        weighted = dict(scores, relevance=min(5.0, scores["relevance"] * theme.weight))
        picks.append(
            Pick(
                arxiv_id=paper.arxiv_id,
                title=paper.title,
                url=paper.url,
                authors=paper.authors,
                abstract=paper.abstract,
                theme=theme.name,
                emoji=theme.emoji,
                scores=scores,
                overall=topics.overall(weighted),
            )
        )
    return picks


def score_papers(
    papers: list[Paper], topics: Topics, llm: Gemini, batch_size: int = 30
) -> list[Pick]:
    picks: list[Pick] = []
    for start in range(0, len(papers), batch_size):
        batch = papers[start : start + batch_size]
        try:
            data = llm.json(build_prompt(batch, topics))
        except LLMError as exc:
            log.error("Scoring batch failed: %s", exc)
            continue
        picks.extend(parse_scores(data, batch, topics))
    log.info("Scored %d of %d candidates", len(picks), len(papers))
    return picks


def select_diverse(picks: list[Pick], count: int, max_per_theme: int = 2) -> list[Pick]:
    """Best overall first, but no more than max_per_theme papers from one theme."""
    chosen: list[Pick] = []
    per_theme: dict[str, int] = {}
    for pick in sorted(picks, key=lambda p: p.overall, reverse=True):
        if per_theme.get(pick.theme, 0) >= max_per_theme:
            continue
        chosen.append(pick)
        per_theme[pick.theme] = per_theme.get(pick.theme, 0) + 1
        if len(chosen) == count:
            break
    return chosen


def describe(picks: list[Pick]) -> str:
    """Compact JSON of picks, used as input for the weekly synthesis."""
    return json.dumps(
        [{"title": p.title, "theme": p.theme, "in_short": p.card.get("in_short", "")}
         for p in picks],
        ensure_ascii=False,
    )
