from pipeline.prefilter import prefilter
from pipeline.schema import Item

KEYWORDS = {
    "include": ["llama", "gguf"],
    "exclude": ["hiring"],
}


def make(title, source_type="reddit", **engagement):
    return Item.make(source_type=source_type, source_name="t", title=title,
                     url=f"https://example.com/{abs(hash(title))}",
                     created_at="2026-08-11T00:00:00+00:00",
                     engagement=engagement)


def test_keyword_match_passes():
    items = prefilter([make("New Llama variant dropped")], KEYWORDS)
    assert len(items) == 1


def test_low_engagement_no_keyword_dropped():
    items = prefilter([make("random gaming post", points=5)], KEYWORDS)
    assert items == []


def test_high_engagement_passes_without_keyword():
    items = prefilter([make("interesting systems post", points=500)], KEYWORDS)
    assert len(items) == 1


def test_exclude_beats_include():
    items = prefilter([make("hiring: llama engineer", points=999)], KEYWORDS)
    assert items == []


def test_watchlist_release_always_passes():
    items = prefilter([make("v1.2.3", source_type="github_release")], KEYWORDS)
    assert len(items) == 1
