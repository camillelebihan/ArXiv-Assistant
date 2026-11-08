from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from src.arxiv_client import Paper, build_query, is_relevant, parse_feed
from src.main import seconds_until
from src.storage import SeenStore
from src.summarizer import Explanation, fallback_summary, parse_response
from src.telegram import TELEGRAM_LIMIT, build_messages, stars

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2611.01234v1</id>
    <published>2026-11-07T18:00:00Z</published>
    <title>Foundation Models
      for Asset Pricing</title>
    <summary>We study pricing. We propose a model. It works.</summary>
    <author><name>A. Author</name></author>
    <author><name>B. Author</name></author>
    <category term="q-fin.ST"/>
  </entry>
</feed>"""


def make_paper(**kwargs) -> Paper:
    defaults = {
        "arxiv_id": "1",
        "title": "A paper",
        "abstract": "Something about vision transformers.",
        "authors": ["X"],
        "url": "http://arxiv.org/abs/1",
        "published": datetime(2026, 11, 7, tzinfo=UTC),
        "categories": ["cs.LG"],
    }
    defaults.update(kwargs)
    return Paper(**defaults)


def test_build_query():
    assert build_query(["q-fin.ST", "cs.LG"]) == "cat:q-fin.ST OR cat:cs.LG"


def test_parse_feed():
    [paper] = parse_feed(SAMPLE_FEED)
    assert paper.arxiv_id == "2611.01234v1"
    assert paper.title == "Foundation Models for Asset Pricing"
    assert paper.authors == ["A. Author", "B. Author"]
    assert paper.categories == ["q-fin.ST"]


def test_qfin_always_relevant():
    assert is_relevant(make_paper(categories=["q-fin.TR"]), ["finance"])


def test_cslg_needs_keyword():
    assert not is_relevant(make_paper(), ["finance"])
    assert is_relevant(make_paper(abstract="LLMs for stock returns"), ["stock"])


def test_fallback_summary():
    paper = make_paper(abstract="First sentence. Second. Third.")
    assert fallback_summary(paper).tldr == "First sentence."


def test_parse_response_full():
    text = (
        '{"tldr": "Predicts returns.", "analogy": "Like a weather forecast.", '
        '"why_it_matters": "Cheaper research.", "score": 4, "score_reason": "Solid data."}'
    )
    exp = parse_response(text, make_paper())
    assert exp.tldr == "Predicts returns."
    assert exp.analogy == "Like a weather forecast."
    assert exp.score == 4


def test_parse_response_bad_json_falls_back():
    paper = make_paper(abstract="Only sentence.")
    assert parse_response("not json", paper).tldr == "Only sentence."


def test_parse_response_invalid_score_dropped():
    exp = parse_response('{"tldr": "x", "score": 9}', make_paper())
    assert exp.score is None


def test_stars():
    assert stars(3) == "★★★☆☆"
    assert stars(None) == ""


def test_one_message_per_paper_sorted_and_escaped():
    weak = (make_paper(arxiv_id="a", title="<script> & co"), Explanation("x", score=2))
    strong = (make_paper(arxiv_id="b", title="Strong"), Explanation("y", score=5))
    messages = build_messages([weak, strong], date(2026, 11, 8))
    assert len(messages) == 3  # intro + 2 papers
    assert "Strong" in messages[1]  # best first
    assert "&lt;script&gt;" in messages[2]
    assert all(len(m) <= TELEGRAM_LIMIT for m in messages)


def test_card_skips_missing_fields():
    [_, card] = build_messages([(make_paper(), Explanation("Just a summary"))], date(2026, 11, 8))
    assert "In short" in card
    assert "Picture it" not in card
    assert "Worth reading" not in card


def test_empty_digest():
    [message] = build_messages([], date(2026, 11, 8))
    assert "No new relevant papers" in message


def test_seen_store():
    store = SeenStore(":memory:")
    assert not store.is_seen("a")
    store.mark_seen(["a", "a"])
    assert store.is_seen("a")


def test_seconds_until_rolls_to_next_day():
    now = datetime(2026, 11, 8, 9, 0, tzinfo=ZoneInfo("Europe/Paris"))
    assert seconds_until("08:00", "Europe/Paris", now) == 23 * 3600
    assert seconds_until("10:00", "Europe/Paris", now) == 3600
