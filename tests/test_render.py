import json
import xml.etree.ElementTree as ET

from pipeline.render import build_feed_json, build_rss, write_day_archive
from pipeline.schema import Item


def _day_items():
    item = Item.make(source_type="rss", source_name="Blog <X>", title="Qwen & friends",
                     url="https://example.com/post?a=1&b=2",
                     created_at="2026-08-11T05:00:00+00:00")
    item.summary = 'A "great" release & more'
    item.importance = 8
    item.category = "new-model-release"
    return [item.to_dict()]


def test_feed_json_merges_days_and_applies_overrides(tmp_path):
    days = tmp_path / "days"
    write_day_archive(days, "2026-08-11", _day_items(), {"rss": {"ok": True, "count": 1}})
    item_id = _day_items()[0]["id"]

    feed = build_feed_json(days, tmp_path / "feed.json", {item_id: {"pinned": True}})
    assert feed["days"][0]["items"][0]["pinned"] is True
    assert json.loads((tmp_path / "feed.json").read_text())["sources_status"]["rss"]["ok"]

    hidden = build_feed_json(days, tmp_path / "feed.json", {item_id: {"hidden": True}})
    assert hidden["days"][0]["items"] == []


def test_rss_is_well_formed_xml(tmp_path):
    days = tmp_path / "days"
    write_day_archive(days, "2026-08-11", _day_items(), {})
    feed = build_feed_json(days, tmp_path / "feed.json", {})
    rss_path = tmp_path / "feed.xml"
    build_rss(feed, rss_path, "https://sqp.github.io/tracker/")

    root = ET.parse(rss_path).getroot()  # raises if malformed despite & and < in input
    assert root.tag == "rss"
    titles = [t.text for t in root.iter("title")]
    assert any("Qwen & friends" in t for t in titles)
