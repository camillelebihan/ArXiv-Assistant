"""Fetch recent papers from the arXiv API and pre-select them by theme."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import requests

from .topics import Topics

log = logging.getLogger("arxiv-digest")

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "arxiv-digest-bot (github.com/camillelebihan/ArXiv-Assistant)"


@dataclass
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    url: str
    published: datetime
    categories: list[str]
    themes: list[str] = field(default_factory=list)
    match_score: float = 0.0


def build_query(categories: list[str]) -> str:
    return " OR ".join(f"cat:{c}" for c in categories)


def parse_feed(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall(f"{ATOM}entry"):
        raw_id = entry.findtext(f"{ATOM}id", default="")
        published = entry.findtext(f"{ATOM}published", default="")
        if not raw_id or not published:
            continue
        papers.append(
            Paper(
                arxiv_id=raw_id.rsplit("/abs/", 1)[-1],
                title=" ".join(entry.findtext(f"{ATOM}title", default="").split()),
                abstract=" ".join(entry.findtext(f"{ATOM}summary", default="").split()),
                authors=[
                    a.findtext(f"{ATOM}name", default="")
                    for a in entry.findall(f"{ATOM}author")
                ],
                url=raw_id.replace("http://", "https://"),
                published=datetime.fromisoformat(published.replace("Z", "+00:00")),
                categories=[c.get("term", "") for c in entry.findall(f"{ATOM}category")],
            )
        )
    return papers


def tag_themes(paper: Paper, topics: Topics) -> Paper:
    """Attach matching themes and a keyword score; excluded papers get no themes."""
    text = f"{paper.title} {paper.abstract}".lower()
    if any(e in text for e in topics.exclude):
        return paper
    scored = [(t, t.hits(text)) for t in topics.themes]
    matched = sorted(((t, h) for t, h in scored if h), key=lambda x: -x[1] * x[0].weight)
    paper.themes = [t.name for t, _ in matched]
    paper.match_score = sum(h * t.weight for t, h in matched)
    return paper


def fetch_recent(
    topics: Topics,
    lookback_hours: int,
    page_size: int = 500,
    max_pages: int = 6,
    now: datetime | None = None,
) -> list[Paper]:
    """Page through the newest papers until the lookback window is covered."""
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=lookback_hours)
    query = build_query(topics.categories)
    papers: list[Paper] = []

    for page in range(max_pages):
        if page:
            time.sleep(3)  # arXiv asks for a pause between requests
        response = requests.get(
            ARXIV_API,
            params={
                "search_query": query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": page * page_size,
                "max_results": page_size,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=60,
        )
        response.raise_for_status()
        batch = parse_feed(response.text)
        papers.extend(p for p in batch if p.published >= cutoff)
        if not batch or batch[-1].published < cutoff:
            break

    log.info("arXiv: %d papers in the last %dh", len(papers), lookback_hours)
    return papers


def preselect(papers: list[Paper], topics: Topics, limit: int) -> list[Paper]:
    """Keep the papers with the strongest theme match, for Gemini to score."""
    tagged = [tag_themes(p, topics) for p in papers]
    matched = [p for p in tagged if p.themes]
    matched.sort(key=lambda p: p.match_score, reverse=True)
    return matched[:limit]
