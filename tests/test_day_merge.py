import json

from pipeline.render import write_day_archive


def test_same_day_rerun_merges_instead_of_overwriting(tmp_path):
    write_day_archive(tmp_path, "2026-08-12",
                      [{"id": "a", "importance": 5}], {"rss": {"ok": True}})
    # second run of the same day carries only a new item
    write_day_archive(tmp_path, "2026-08-12",
                      [{"id": "b", "importance": 8}], {"rss": {"ok": True}})

    day = json.loads((tmp_path / "2026-08-12.json").read_text())
    ids = [it["id"] for it in day["items"]]
    assert ids == ["b", "a"]  # both present, sorted by importance


def test_rerun_updates_existing_item(tmp_path):
    write_day_archive(tmp_path, "2026-08-12", [{"id": "a", "importance": 2}], {})
    write_day_archive(tmp_path, "2026-08-12", [{"id": "a", "importance": 9}], {})
    day = json.loads((tmp_path / "2026-08-12.json").read_text())
    assert len(day["items"]) == 1
    assert day["items"][0]["importance"] == 9
