"""Reader-friendly paper explanations with Gemini."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .arxiv_client import Paper

PROMPT = """You explain new research papers to a smart reader who is not a specialist.
Use plain English, no jargon, no hype. Each field is at most 25 words.

Return JSON with exactly these keys:
- "tldr": what the paper does, in one sentence.
- "analogy": an everyday visual analogy for the main idea ("It's like ...").
- "why_it_matters": what this could change in finance, AI or the real world.
- "score": integer 1-5, how promising the paper looks from its abstract
  (novelty, clear results, real-world relevance).
- "score_reason": one short reason for the score, including a caveat if any.

Title: {title}
Abstract: {abstract}
"""


@dataclass
class Explanation:
    tldr: str
    analogy: str = ""
    why_it_matters: str = ""
    score: int | None = None
    score_reason: str = ""


def fallback_summary(paper: Paper) -> Explanation:
    """Used when the LLM call fails: the abstract's first sentence."""
    first = paper.abstract.split(". ")[0].strip().rstrip(".")
    return Explanation(tldr=first + "." if first else paper.title)


def parse_response(text: str, paper: Paper) -> Explanation:
    """Turn Gemini's JSON into an Explanation, tolerating missing fields."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return fallback_summary(paper)
    if not isinstance(data, dict) or not data.get("tldr"):
        return fallback_summary(paper)

    score = data.get("score")
    if not isinstance(score, int) or not 1 <= score <= 5:
        score = None

    return Explanation(
        tldr=str(data["tldr"]).strip(),
        analogy=str(data.get("analogy", "")).strip(),
        why_it_matters=str(data.get("why_it_matters", "")).strip(),
        score=score,
        score_reason=str(data.get("score_reason", "")).strip(),
    )


class Summarizer:
    def __init__(self, api_key: str, model: str):
        from google import genai  # imported lazily so tests don't need credentials

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def summarize(self, paper: Paper) -> Explanation:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=PROMPT.format(title=paper.title, abstract=paper.abstract),
                config={"response_mime_type": "application/json"},
            )
            return parse_response(response.text, paper)
        except Exception:  # never let one paper break the digest
            return fallback_summary(paper)
