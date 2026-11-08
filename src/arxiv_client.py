"""Fetch and filter recent papers from the arXiv API."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    url: str
    published: datetime
    categories: list[str]


def build_query(categories: list[str]) -> str:
    return " OR ".join(f"cat:{c}" for c in categories)


def parse_feed(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall(f"{ATOM}entry"):
        raw_id = entry.findtext(f"{ATOM}id", default="")
        arxiv_id = raw_id.rsplit("/abs/", 1)[-1]
        published = datetime.fromisoformat(
            entry.findtext(f"{ATOM}published", default="").replace("Z", "+00:00")
        )
        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=" ".join(entry.findtext(f"{ATOM}title", default="").split()),
                abstract=" ".join(entry.findtext(f"{ATOM}summary", default="").split()),
                authors=[
                    a.findtext(f"{ATOM}name", default="")
                    for a in entry.findall(f"{ATOM}author")
                ],
                url=raw_id,
                published=published,
                categories=[c.get("term", "") for c in entry.findall(f"{ATOM}category")],
            )
        )
    return papers


def is_relevant(paper: Paper, keywords: list[str]) -> bool:
    """q-fin papers are always relevant; cs.LG papers must match a keyword."""
    if any(c.startswith("q-fin") for c in paper.categories):
        return True
    text = f"{paper.title} {paper.abstract}".lower()
    return any(k.lower() in text for k in keywords)


def fetch_recent(
    categories: list[str],
    keywords: list[str],
    lookback_hours: int,
    max_results: int = 200,
    now: datetime | None = None,
) -> list[Paper]:
    params = {
        "search_query": build_query(categories),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    response = requests.get(ARXIV_API, params=params, timeout=30)
    response.raise_for_status()

    cutoff = (now or datetime.now(UTC)) - timedelta(hours=lookback_hours)
    return [
        p
        for p in parse_feed(response.text)
        if p.published >= cutoff and is_relevant(p, keywords)
    ]
