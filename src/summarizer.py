"""Three-line paper summaries with Gemini."""

from __future__ import annotations

from .arxiv_client import Paper

PROMPT = """You summarise research papers for a busy reader in finance and machine learning.
Write exactly 3 short lines, no title, no bullet symbols:
1. The problem the paper tackles.
2. The method.
3. The main result or why it matters.

Title: {title}
Abstract: {abstract}
"""


def fallback_summary(paper: Paper) -> str:
    """Used when the LLM call fails: first sentences of the abstract."""
    sentences = paper.abstract.split(". ")
    return ". ".join(sentences[:2]).strip()


class Summarizer:
    def __init__(self, api_key: str, model: str):
        from google import genai  # imported lazily so tests don't need credentials

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def summarize(self, paper: Paper) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=PROMPT.format(title=paper.title, abstract=paper.abstract),
            )
            text = (response.text or "").strip()
            return text or fallback_summary(paper)
        except Exception:  # never let one paper break the digest
            return fallback_summary(paper)
