"""Load topics.toml: reader profile, categories, themes, scoring weights."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Theme:
    name: str
    emoji: str
    description: str
    keywords: list[str]
    weight: float = 1.0
    _patterns: list[re.Pattern[str]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        # Match keywords at a word start, so "agent" matches "agents" but not "reagent".
        self._patterns = [re.compile(r"\b" + re.escape(k.lower())) for k in self.keywords]

    def hits(self, text: str) -> int:
        return sum(1 for p in self._patterns if p.search(text))


@dataclass
class Topics:
    profile: str
    categories: list[str]
    themes: list[Theme]
    exclude: list[str]
    weights: dict[str, float]

    def theme(self, name: str) -> Theme | None:
        return next((t for t in self.themes if t.name == name), None)

    def overall(self, scores: dict[str, int]) -> float:
        total = sum(self.weights.values()) or 1.0
        value = sum(scores.get(axis, 0) * w for axis, w in self.weights.items()) / total
        return round(value, 2)


DEFAULT_WEIGHTS = {"novelty": 0.25, "rigor": 0.2, "impact": 0.3, "relevance": 0.25}


def load_topics(path: str | Path) -> Topics:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    themes = [
        Theme(
            name=t["name"],
            emoji=t.get("emoji", "•"),
            description=t.get("description", ""),
            keywords=t.get("keywords", []),
            weight=float(t.get("weight", 1.0)),
        )
        for t in data.get("theme", [])
    ]
    if not themes:
        raise ValueError(f"{path} defines no [[theme]] entries")
    return Topics(
        profile=" ".join(data.get("profile", "").split()),
        categories=data.get("categories", ["cs.AI", "cs.LG"]),
        themes=themes,
        exclude=[e.lower() for e in data.get("exclude", [])],
        weights={**DEFAULT_WEIGHTS, **data.get("scoring", {})},
    )
