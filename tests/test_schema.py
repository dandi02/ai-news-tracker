from pipeline.schema import Item, canonical_url, item_id


def test_canonical_strips_tracking_and_www():
    a = canonical_url("https://www.example.com/post/?utm_source=x&utm_campaign=y")
    b = canonical_url("https://example.com/post")
    assert a == b


def test_canonical_keeps_meaningful_query():
    url = canonical_url("https://example.com/watch?v=abc123")
    assert "v=abc123" in url


def test_id_stable_across_variants():
    assert item_id("https://Example.com/foo/") == item_id("http://www.example.com/foo")


def test_id_without_url_uses_native():
    assert item_id("", native_id="abc") == item_id("", native_id="abc")
    assert item_id("", native_id="abc") != item_id("", native_id="def")


def test_item_make_truncates_title():
    item = Item.make(source_type="rss", source_name="t", title="x" * 500,
                     url="https://example.com/a", created_at="2026-08-11T00:00:00+00:00")
    assert len(item.title) == 300
    assert item.to_dict()["source_type"] == "rss"
