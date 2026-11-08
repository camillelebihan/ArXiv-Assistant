"""Plain-JSON state: what was sent, and every daily and weekly digest.

JSON (not a database) so the state can live in git and feed the website.
Layout inside the data folder:
    meta.json            last daily date and last weekly ISO week sent
    seen.json            arXiv ids already sent, with the date (pruned after 60 days)
    days/YYYY-MM-DD.json the papers of one daily digest
    weeks/YYYY-Www.json  one weekly digest
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .ranker import Pick

SEEN_DAYS = 60


class State:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "days").mkdir(parents=True, exist_ok=True)
        (self.root / "weeks").mkdir(parents=True, exist_ok=True)

    # --- helpers -----------------------------------------------------------
    def _read(self, name: str, default):
        path = self.root / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, name: str, data) -> None:
        path = self.root / name
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # --- meta --------------------------------------------------------------
    @property
    def meta(self) -> dict:
        return self._read("meta.json", {})

    def set_meta(self, **values: str) -> None:
        self._write("meta.json", {**self.meta, **values})

    # --- seen --------------------------------------------------------------
    def seen_ids(self) -> set[str]:
        return set(self._read("seen.json", {}))

    def mark_seen(self, arxiv_ids: list[str], today: date) -> None:
        seen = self._read("seen.json", {})
        seen.update({i: today.isoformat() for i in arxiv_ids})
        cutoff = (today - timedelta(days=SEEN_DAYS)).isoformat()
        self._write("seen.json", {i: d for i, d in seen.items() if d >= cutoff})

    # --- digests -----------------------------------------------------------
    def save_day(self, day: date, picks: list[Pick]) -> None:
        """Add picks to the day's digest; a second run the same day never erases the first."""
        existing = self.load_day(day.isoformat())
        known = {p.arxiv_id for p in existing}
        merged = existing + [p for p in picks if p.arxiv_id not in known]
        self._write(
            f"days/{day.isoformat()}.json",
            {"date": day.isoformat(), "picks": [p.to_dict() for p in merged]},
        )

    def load_day(self, day: str) -> list[Pick]:
        data = self._read(f"days/{day}.json", {"picks": []})
        return [Pick.from_dict(p) for p in data["picks"]]

    def days(self) -> list[str]:
        return sorted((p.stem for p in (self.root / "days").glob("*.json")), reverse=True)

    def picks_between(self, start: date, end: date) -> list[Pick]:
        """All papers from daily digests with start <= date <= end."""
        out: list[Pick] = []
        for day in self.days():
            if start.isoformat() <= day <= end.isoformat():
                out.extend(self.load_day(day))
        return out

    def save_week(self, week: str, label: str, synthesis: dict, picks: list[Pick]) -> None:
        self._write(
            f"weeks/{week}.json",
            {"week": week, "label": label, "synthesis": synthesis,
             "picks": [p.to_dict() for p in picks]},
        )

    def load_week(self, week: str) -> dict:
        data = self._read(f"weeks/{week}.json", {})
        data["picks"] = [Pick.from_dict(p) for p in data.get("picks", [])]
        return data

    def weeks(self) -> list[str]:
        return sorted((p.stem for p in (self.root / "weeks").glob("*.json")), reverse=True)
