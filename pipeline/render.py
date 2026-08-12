"""Render outputs: per-day archive, merged feed.json, and RSS feed.xml (stdlib only)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

FEED_WINDOW_DAYS = 30
RSS_ITEMS = 40


def write_day_archive(days_dir: Path, day: str, items: list[dict],
                      sources_status: dict) -> None:
    days_dir.mkdir(parents=True, exist_ok=True)
    (days_dir / f"{day}.json").write_text(json.dumps({
        "date": day,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "sources_status": sources_status,
        "items": items,
    }, ensure_ascii=False, indent=1))


def build_feed_json(days_dir: Path, feed_path: Path, overrides: dict) -> dict:
    """Merge the last FEED_WINDOW_DAYS day-archives into site/data/feed.json.

    Overrides are re-applied at merge time so pins/hides done after a day was
    archived still take effect on the published feed.
    """
    day_files = sorted(days_dir.glob("*.json"), reverse=True)[:FEED_WINDOW_DAYS]
    days = []
    for f in day_files:
        try:
            day = json.loads(f.read_text())
        except json.JSONDecodeError:
            log.warning("skipping corrupt day archive %s", f)
            continue
        items = []
        for item in day.get("items", []):
            ov = overrides.get(item["id"], {})
            if ov.get("hidden"):
                continue
            item["pinned"] = bool(ov.get("pinned", item.get("pinned")))
            item["tags"] = list(ov.get("tags", item.get("tags", [])))
            items.append(item)
        day["items"] = items
        days.append(day)

    feed = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "sources_status": days[0]["sources_status"] if days else {},
        "days": days,
    }
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text(json.dumps(feed, ensure_ascii=False))
    return feed


def build_rss(feed: dict, rss_path: Path, site_url: str) -> None:
    items_xml = []
    count = 0
    for day in feed.get("days", []):
        for item in day.get("items", []):
            if count >= RSS_ITEMS:
                break
            title = escape(item.get("title", ""))
            summary = escape(item.get("summary", "") or item.get("snippet", ""))
            source = escape(item.get("source_name", ""))
            category = escape(item.get("category", ""))
            url = escape(item.get("url", ""), {'"': "&quot;"})
            try:
                pub = format_datetime(datetime.fromisoformat(
                    item.get("created_at").replace("Z", "+00:00")))
            except (ValueError, AttributeError):
                pub = format_datetime(datetime.now(tz=timezone.utc))
            items_xml.append(
                f"  <item>\n"
                f"    <title>[{category}] {title}</title>\n"
                f"    <link>{url}</link>\n"
                f"    <guid isPermaLink=\"false\">{item['id']}</guid>\n"
                f"    <pubDate>{pub}</pubDate>\n"
                f"    <description>{summary} (via {source}, importance "
                f"{item.get('importance', '?')}/10)</description>\n"
                f"  </item>"
            )
            count += 1

    now = format_datetime(datetime.now(tz=timezone.utc))
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n<channel>\n'
        "  <title>SQP AI News Tracker</title>\n"
        f"  <link>{escape(site_url)}</link>\n"
        "  <description>Daily curated open-source LLM news for SQP developers</description>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(items_xml)
        + "\n</channel>\n</rss>\n"
    )
    rss_path.write_text(rss)
