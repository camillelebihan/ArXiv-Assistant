from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from src.arxiv_client import Paper, build_query, is_relevant, parse_feed
from src.main import seconds_until
from src.storage import SeenStore
from src.summarizer import fallback_summary
from src.telegram import TELEGRAM_LIMIT, build_messages

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
    paper = make_paper(abstract="First. Second. Third.")
    assert fallback_summary(paper) == "First. Second"


def test_messages_escape_html_and_respect_limit():
    paper = make_paper(title="<script> & co")
    items = [(paper, "x" * 1500)] * 10
    messages = build_messages(items, date(2026, 11, 8))
    assert all(len(m) <= TELEGRAM_LIMIT for m in messages)
    assert "&lt;script&gt;" in messages[0]


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
