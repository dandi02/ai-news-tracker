"""Generic RSS/Atom fetcher (blogs, arXiv) plus YouTube channel feeds."""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone

import feedparser

from .. import http
from ..schema import Item

log = logging.getLogger(__name__)


def _entry_time(entry) -> str:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc).isoformat()
    return datetime.now(tz=timezone.utc).isoformat()


def _snippet(entry) -> str:
    text = getattr(entry, "summary", "") or ""
    if getattr(entry, "content", None):
        text = entry.content[0].get("value", text)
    # crude tag strip; good enough for a snippet
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()[:400]


def _parse_feed(url: str, name: str, source_type: str, keywords: dict,
                keyword_gate: bool = False, max_items: int = 0) -> list[Item]:
    resp = http.get(url, conditional=True)
    if resp is None:  # 304 — nothing new
        return []
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        log.warning("unparseable feed %s: %s", url, parsed.get("bozo_exception"))
        return []

    include = [k.lower() for k in keywords.get("include", [])]
    items: list[Item] = []
    for entry in parsed.entries:
        link = getattr(entry, "link", "")
        title = getattr(entry, "title", "")
        if not link or not title:
            continue
        if keyword_gate:
            haystack = (title + " " + _snippet(entry)).lower()
            if not any(k in haystack for k in include):
                continue
        items.append(Item.make(
            source_type=source_type,
            source_name=name,
            title=title,
            url=link,
            created_at=_entry_time(entry),
            author=getattr(entry, "author", ""),
            snippet=_snippet(entry),
        ))
        if max_items and len(items) >= max_items:
            break
    return items


def fetch(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    items: list[Item] = []
    for feed in sources.get("feeds", []):
        if not feed.get("enabled", True):
            continue
        try:
            got = _parse_feed(
                feed["url"], feed.get("name", feed["url"]), "rss", keywords,
                keyword_gate=feed.get("keyword_gate", False),
                max_items=feed.get("max_items", 0) or (limit or 0),
            )
            items.extend(got[: limit or None])
        except Exception as exc:  # noqa: BLE001 — one bad feed must not kill the rest
            log.warning("feed failed %s: %s", feed.get("name"), exc)
    return items


def fetch_youtube(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    items: list[Item] = []
    for chan in sources.get("youtube", []):
        if not chan.get("enabled", True):
            continue
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={chan['channel_id']}"
        try:
            got = _parse_feed(url, chan.get("name", chan["channel_id"]), "youtube",
                              keywords, keyword_gate=True)
            items.extend(got[: limit or None])
        except Exception as exc:  # noqa: BLE001
            log.warning("youtube channel failed %s: %s", chan.get("name"), exc)
    return items
