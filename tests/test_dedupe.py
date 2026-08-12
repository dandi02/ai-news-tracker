from pipeline.dedupe import dedupe, mark_seen
from pipeline.schema import Item


def make(url, source_name="a", external_url="", **engagement):
    return Item.make(source_type="reddit", source_name=source_name, title=url,
                     url=url, external_url=external_url,
                     created_at="2026-08-11T00:00:00+00:00", engagement=engagement)


def test_seen_items_dropped():
    item = make("https://example.com/one")
    assert dedupe([item], {item.id: "2026-08-10"}) == []


def test_cross_source_merge_keeps_highest_engagement():
    a = make("https://reddit.com/r/x/1", "r/x",
             external_url="https://blog.example.com/post", points=10)
    b = make("https://news.ycombinator.com/item?id=2", "Hacker News",
             external_url="https://blog.example.com/post", points=300)
    merged = dedupe([a, b], {})
    assert len(merged) == 1
    assert merged[0].source_name == "Hacker News"
    assert merged[0].also_on[0]["source_name"] == "r/x"


def test_distinct_urls_not_merged():
    merged = dedupe([make("https://example.com/a"), make("https://example.com/b")], {})
    assert len(merged) == 2


def test_mark_seen_adds_ids():
    seen = {}
    item = make("https://example.com/one")
    mark_seen(seen, [item])
    assert item.id in seen
