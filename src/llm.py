"""Thin Gemini wrapper: JSON answers, spacing between calls, retries, visible errors."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger("arxiv-digest")


class LLMError(RuntimeError):
    pass


def extract_json(text: str | None) -> Any:
    """Parse JSON, tolerating a ```json fenced block around it."""
    if not text:
        raise LLMError("empty response")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError(f"response was not valid JSON: {exc}") from exc


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def _is_daily_quota(exc: Exception) -> bool:
    """The per-day quota resets at midnight Pacific time: retrying today is pointless."""
    return "PerDay" in str(exc)


class Gemini:
    def __init__(self, api_key: str, model: str, min_interval: float = 4.0, retries: int = 3):
        from google import genai  # imported lazily so tests don't need credentials

        # JSON mode is only available on the v1beta API, not the stable v1 the SDK defaults to.
        self._client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        self.model = model
        self._min_interval = min_interval
        self._retries = retries
        self._last_call = 0.0

    def _wait_turn(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def json(self, prompt: str) -> Any:
        """Ask for a JSON answer. Raises LLMError with the real reason on failure."""
        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            self._wait_turn()
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                return extract_json(response.text)
            except LLMError as exc:
                last_error = exc
                log.warning("Gemini attempt %d: %s", attempt, exc)
            except Exception as exc:  # SDK raises several error types
                last_error = exc
                log.warning("Gemini attempt %d failed: %s", attempt, exc)
                if not _is_rate_limit(exc) or _is_daily_quota(exc):
                    break
                time.sleep(20 * attempt)
        raise LLMError(str(last_error))
