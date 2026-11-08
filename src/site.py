"""Static website: an index, one page per daily digest and per weekly digest."""

from __future__ import annotations

import html
import logging
import shutil
from datetime import date
from pathlib import Path

from .ranker import Pick
from .state import State
from .telegram import LABELS, SCORE_LABELS

log = logging.getLogger("arxiv-digest")
e = html.escape
STYLE = Path(__file__).with_name("style.css")


def page(title: str, body: str, root: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<link rel="stylesheet" href="{root}style.css">
</head>
<body>
<header class="top"><a href="{root}index.html" class="brand">ArXiv Assistant</a>
<span class="tag">AI research for innovators</span></header>
<main>
{body}
</main>
<footer>Papers from <a href="https://arxiv.org">arXiv</a>. Summaries and scores are written by
Gemini from abstracts only: a first impression, not a peer review.</footer>
</body>
</html>
"""


def score_rows(pick: Pick) -> str:
    rows = []
    for axis, label in SCORE_LABELS.items():
        value = pick.scores.get(axis, 1)
        rows.append(
            f'<div class="score"><span>{label}</span>'
            f'<span class="bar"><i style="width:{value * 20}%"></i></span>'
            f"<b>{value}</b></div>"
        )
    return "".join(rows)


def card(pick: Pick) -> str:
    authors = ", ".join(pick.authors[:3]) + (" et al." if len(pick.authors) > 3 else "")
    bullets = "".join(
        f"<li><b>{label}</b> {e(pick.card[key])}</li>"
        for key, label in LABELS.items()
        if pick.card.get(key)
    )
    return f"""<article class="card">
  <div class="meta"><span class="theme">{pick.emoji} {e(pick.theme)}</span>
  <span class="overall">{pick.overall:.1f}<small>/5</small></span></div>
  <h2><a href="{e(pick.url)}">{e(pick.title)}</a></h2>
  <p class="authors">{e(authors)}</p>
  <ul>{bullets}</ul>
  <div class="scores">{score_rows(pick)}</div>
</article>"""


def pretty_day(day: str) -> str:
    return date.fromisoformat(day).strftime("%A %-d %B %Y")


def build_site(state: State, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    (out / "days").mkdir(parents=True, exist_ok=True)
    (out / "weeks").mkdir(parents=True, exist_ok=True)
    shutil.copy(STYLE, out / "style.css")
    (out / ".nojekyll").touch()

    days, weeks = state.days(), state.weeks()

    for day in days:
        picks = state.load_day(day)
        cards = "".join(card(p) for p in picks) or '<p class="empty">No papers selected.</p>'
        body = f'<h1>{e(pretty_day(day))}</h1><p class="lede">Daily briefing</p>{cards}'
        (out / "days" / f"{day}.html").write_text(page(pretty_day(day), body, "../"), "utf-8")

    for week in weeks:
        data = state.load_week(week)
        synthesis = data.get("synthesis", {})
        trends = "".join(f"<li>{e(t)}</li>" for t in synthesis.get("big_picture", []))
        watch = synthesis.get("watch_next", "")
        intro = ""
        if trends:
            intro += f'<section class="big"><h3>The big picture</h3><ul>{trends}</ul>'
            intro += f"<p><b>Watch next:</b> {e(watch)}</p>" if watch else ""
            intro += "</section>"
        cards = "".join(card(p) for p in data["picks"])
        label = data.get("label", week)
        body = f'<h1>Week in AI</h1><p class="lede">{e(label)}</p>{intro}{cards}'
        (out / "weeks" / f"{week}.html").write_text(page(f"Week {label}", body, "../"), "utf-8")

    latest = ""
    if days:
        picks = state.load_day(days[0])
        latest = (f'<h1>{e(pretty_day(days[0]))}</h1><p class="lede">Latest briefing</p>'
                  + "".join(card(p) for p in picks))
    else:
        latest = "<h1>ArXiv Assistant</h1><p class='lede'>The first briefing is on its way.</p>"

    day_links = "".join(
        f'<li><a href="days/{d}.html">{e(pretty_day(d))}</a></li>' for d in days[:60]
    )
    week_links = "".join(
        f'<li><a href="weeks/{w}.html">{e(state.load_week(w).get("label", w))}</a></li>'
        for w in weeks
    )
    archive = '<section class="archive">'
    if week_links:
        archive += f"<div><h3>Weekly</h3><ul>{week_links}</ul></div>"
    if day_links:
        archive += f"<div><h3>Daily</h3><ul>{day_links}</ul></div>"
    archive += "</section>"

    (out / "index.html").write_text(page("ArXiv Assistant", latest + archive), "utf-8")
    log.info("Website built in %s (%d days, %d weeks)", out, len(days), len(weeks))
    return out
