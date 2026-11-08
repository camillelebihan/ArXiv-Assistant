from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.arxiv_client import Paper, build_query, parse_feed, preselect, tag_themes
from src.llm import LLMError, _is_daily_quota, extract_json
from src.main import due_jobs, week_key, week_label
from src.ranker import Pick, parse_scores, select_diverse
from src.site import build_site
from src.state import State
from src.summarizer import fallback_card, parse_cards
from src.telegram import TELEGRAM_LIMIT, daily_messages, dots, weekly_messages
from src.topics import load_topics

ROOT = Path(__file__).resolve().parent.parent
PARIS = ZoneInfo("Europe/Paris")

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2611.01234v1</id>
    <published>2026-11-07T18:00:00Z</published>
    <title>Humanoid Robots
      that Learn from Video</title>
    <summary>We train a humanoid robot. It works.</summary>
    <author><name>A. Author</name></author>
    <category term="cs.RO"/>
  </entry>
</feed>"""


@pytest.fixture(scope="module")
def topics():
    return load_topics(ROOT / "topics.toml")


def make_paper(**kwargs) -> Paper:
    defaults = {
        "arxiv_id": "1",
        "title": "A paper",
        "abstract": "Something unrelated about wetlands.",
        "authors": ["X"],
        "url": "https://arxiv.org/abs/1",
        "published": datetime(2026, 11, 7, tzinfo=UTC),
        "categories": ["cs.LG"],
    }
    defaults.update(kwargs)
    return Paper(**defaults)


def make_pick(**kwargs) -> Pick:
    defaults = {
        "arxiv_id": "1",
        "title": "Title",
        "url": "https://arxiv.org/abs/1",
        "authors": ["A", "B", "C"],
        "abstract": "First sentence. Second.",
        "theme": "AI agents",
        "emoji": "🤖",
        "scores": {"novelty": 4, "rigor": 3, "impact": 5, "relevance": 4},
        "overall": 4.1,
        "card": {"in_short": "Does a thing.", "ask": "Why now?"},
        "date": "2026-11-09",
    }
    defaults.update(kwargs)
    return Pick(**defaults)


# --- topics & fetching -------------------------------------------------------
def test_topics_file_loads(topics):
    assert len(topics.themes) >= 10
    assert "cs.RO" in topics.categories
    assert topics.theme("AI for finance").weight < 1


def test_keyword_matches_word_start_only(topics):
    agents = topics.theme("AI agents")
    assert agents.hits("multi-agent systems and agents") > 0
    assert agents.hits("a chemical reagent") == 0


def test_parse_feed():
    [paper] = parse_feed(SAMPLE_FEED)
    assert paper.arxiv_id == "2611.01234v1"
    assert paper.title == "Humanoid Robots that Learn from Video"
    assert paper.url.startswith("https://")


def test_build_query():
    assert build_query(["cs.AI", "cs.RO"]) == "cat:cs.AI OR cat:cs.RO"


def test_tagging_and_preselect(topics):
    robot = make_paper(arxiv_id="r", title="Humanoid robot manipulation")
    other = make_paper(arxiv_id="o")
    assert "Robotics & embodied AI" in tag_themes(robot, topics).themes
    assert [p.arxiv_id for p in preselect([robot, other], topics, 10)] == ["r"]


def test_exclude_list(topics):
    paper = make_paper(title="Erratum: robot learning")
    assert tag_themes(paper, topics).themes == []


# --- llm & scoring -----------------------------------------------------------
def test_extract_json_handles_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(LLMError):
        extract_json("not json")


def test_parse_scores_clamps_and_skips_bad_rows(topics):
    papers = [make_paper(arxiv_id="a"), make_paper(arxiv_id="b")]
    data = [
        {"i": 0, "theme": "AI agents", "novelty": 9, "rigor": 0, "impact": 3, "relevance": 4},
        {"i": 7, "theme": "AI agents"},  # out of range
        {"i": 1, "theme": "Not a theme"},  # unknown theme, no fallback
    ]
    [pick] = parse_scores(data, papers, topics)
    assert pick.scores == {"novelty": 5, "rigor": 1, "impact": 3, "relevance": 4}
    assert 1 <= pick.overall <= 5


def test_parse_scores_accepts_wrapped_list(topics):
    data = {"papers": [{"i": 0, "theme": "AI agents", "novelty": 3, "rigor": 3,
                        "impact": 3, "relevance": 3}]}
    assert len(parse_scores(data, [make_paper()], topics)) == 1


def test_finance_weight_lowers_overall(topics):
    row = {"i": 0, "novelty": 4, "rigor": 4, "impact": 4, "relevance": 5}
    agents = parse_scores([dict(row, theme="AI agents")], [make_paper()], topics)[0]
    finance = parse_scores([dict(row, theme="AI for finance")], [make_paper()], topics)[0]
    assert finance.overall < agents.overall


def test_select_diverse_caps_each_theme():
    picks = [make_pick(arxiv_id=str(i), overall=5 - i * 0.1) for i in range(4)]
    picks.append(make_pick(arxiv_id="x", theme="Quantum computing", overall=1.0))
    chosen = select_diverse(picks, count=3, max_per_theme=2)
    assert [p.theme for p in chosen].count("AI agents") == 2
    assert chosen[-1].theme == "Quantum computing"


def test_fallback_card():
    assert fallback_card(make_pick()) == {"in_short": "First sentence."}


def test_parse_cards_matches_by_index_and_falls_back():
    picks = [make_pick(arxiv_id="a"), make_pick(arxiv_id="b")]
    data = [{"i": 1, "in_short": "Second paper.", "ask": "Why?"}, {"i": 0, "picture_it": "x"}]
    cards = parse_cards(data, picks)
    assert cards[0] == {"in_short": "First sentence."}  # row without in_short → fallback
    assert cards[1] == {"in_short": "Second paper.", "ask": "Why?"}


def test_parse_cards_wrapped_and_garbage():
    picks = [make_pick()]
    assert parse_cards({"cards": [{"i": 0, "in_short": "Ok."}]}, picks)[0]["in_short"] == "Ok."
    assert parse_cards("nonsense", picks) == [{"in_short": "First sentence."}]


def test_daily_quota_detection():
    assert _is_daily_quota(Exception("quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    assert not _is_daily_quota(Exception("429 per minute"))


# --- telegram ----------------------------------------------------------------
def test_daily_messages_escape_and_fit():
    picks = [make_pick(title="<b>x</b> & y", card={"in_short": "z" * 3000})]
    intro, card = daily_messages(picks, date(2026, 11, 9))
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in card
    assert "Ask an expert" not in card  # missing field → line skipped
    assert len(card) <= TELEGRAM_LIMIT
    assert "1 paper worth" in intro


def test_daily_empty():
    [message] = daily_messages([], date(2026, 11, 9))
    assert "No strong new papers" in message


def test_weekly_messages():
    synthesis = {"big_picture": ["Agents go mainstream."], "watch_next": "Robots."}
    text = "\n".join(weekly_messages([make_pick()], synthesis, "2–8 Nov 2026"))
    assert "The big picture" in text and "Watch next" in text and "Top 1" in text


def test_dots():
    assert dots(3) == "●●●○○"


# --- schedule ----------------------------------------------------------------
def test_due_jobs_weekday_morning():
    monday_7 = datetime(2026, 11, 9, 7, 10, tzinfo=PARIS)
    assert due_jobs(monday_7, {}, 7, 9) == ["daily"]
    assert due_jobs(monday_7, {"last_daily": "2026-11-09"}, 7, 9) == []
    assert due_jobs(monday_7.replace(hour=6), {}, 7, 9) == []


def test_due_jobs_sunday_and_saturday():
    sunday_9 = datetime(2026, 11, 15, 9, 10, tzinfo=PARIS)
    assert due_jobs(sunday_9, {}, 7, 9) == ["weekly"]
    assert due_jobs(sunday_9, {"last_weekly": week_key(sunday_9.date())}, 7, 9) == []
    saturday = datetime(2026, 11, 14, 10, 0, tzinfo=PARIS)
    assert due_jobs(saturday, {}, 7, 9) == []


def test_week_label():
    assert week_label(date(2026, 11, 15)) == "9–15 Nov 2026"
    assert week_label(date(2026, 11, 1)) == "26 Oct–1 Nov 2026"


# --- state & website ---------------------------------------------------------
def test_state_roundtrip(tmp_path):
    state = State(tmp_path)
    state.save_day(date(2026, 11, 9), [make_pick()])
    state.mark_seen(["1"], date(2026, 11, 9))
    state.set_meta(last_daily="2026-11-09")
    assert state.load_day("2026-11-09")[0].card["ask"] == "Why now?"
    assert "1" in state.seen_ids()
    assert state.meta["last_daily"] == "2026-11-09"
    assert len(state.picks_between(date(2026, 11, 9), date(2026, 11, 15))) == 1


def test_second_run_same_day_keeps_first(tmp_path):
    state = State(tmp_path)
    state.save_day(date(2026, 11, 9), [make_pick(arxiv_id="a")])
    state.save_day(date(2026, 11, 9), [])
    state.save_day(date(2026, 11, 9), [make_pick(arxiv_id="a"), make_pick(arxiv_id="b")])
    assert [p.arxiv_id for p in state.load_day("2026-11-09")] == ["a", "b"]


def test_seen_is_pruned(tmp_path):
    state = State(tmp_path)
    state.mark_seen(["old"], date(2026, 1, 1))
    state.mark_seen(["new"], date(2026, 11, 9))
    assert state.seen_ids() == {"new"}


def test_build_site(tmp_path):
    state = State(tmp_path / "data")
    state.save_day(date(2026, 11, 9), [make_pick(title="Robots <3")])
    state.save_week("2026-W46", "9–15 Nov 2026", {"big_picture": ["Trend"]}, [make_pick()])
    out = build_site(state, tmp_path / "site")
    index = (out / "index.html").read_text()
    assert "Robots &lt;3" in index
    assert "weeks/2026-W46.html" in index
    assert (out / "days" / "2026-11-09.html").exists()
    assert "The big picture" in (out / "weeks" / "2026-W46.html").read_text()
    assert (out / "style.css").exists()
