"""Reddit via public JSON endpoints (no OAuth); falls back to RSS on 403/429."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .. import http
from ..schema import Item

log = logging.getLogger(__name__)


def _json_items(sub: str, limit: int) -> list[Item]:
    resp = http.get(f"https://www.reddit.com/r/{sub}/top.json",
                    params={"t": "day", "limit": limit})
    items = []
    for child in resp.json().get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("stickied"):
            continue
        permalink = f"https://www.reddit.com{post.get('permalink', '')}"
        external = post.get("url_overridden_by_dest") or ""
        items.append(Item.make(
            source_type="reddit",
            source_name=f"r/{sub}",
            title=post.get("title", ""),
            url=permalink,
            external_url=external if external != permalink else "",
            created_at=datetime.fromtimestamp(
                post.get("created_utc", 0), tz=timezone.utc).isoformat(),
            author=post.get("author", ""),
            snippet=(post.get("selftext") or "")[:400],
            engagement={"points": post.get("score", 0),
                        "comments": post.get("num_comments", 0)},
            native_id=post.get("name"),
        ))
    return items


def _rss_fallback(sub: str, keywords: dict) -> list[Item]:
    from . import rss as rss_mod
    return rss_mod._parse_feed(
        f"https://www.reddit.com/r/{sub}/top/.rss?t=day",
        f"r/{sub}", "reddit", keywords)


def fetch(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    items: list[Item] = []
    for sub_cfg in sources.get("reddit", []):
        if not sub_cfg.get("enabled", True):
            continue
        sub = sub_cfg["name"]
        try:
            items.extend(_json_items(sub, limit or 50))
        except Exception as exc:  # noqa: BLE001 — fall back to RSS, then keep going
            log.warning("reddit JSON failed for r/%s (%s); trying RSS", sub, exc)
            try:
                items.extend(_rss_fallback(sub, keywords)[: limit or None])
            except Exception as exc2:  # noqa: BLE001
                log.warning("reddit RSS fallback failed for r/%s: %s", sub, exc2)
    return items
