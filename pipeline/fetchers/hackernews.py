"""Hacker News via the Algolia search API (no auth)."""

from __future__ import annotations

import logging
import time

from .. import http
from ..schema import Item

log = logging.getLogger(__name__)

API = "https://hn.algolia.com/api/v1"


def _to_item(hit: dict) -> Item:
    hn_url = f"https://news.ycombinator.com/item?id={hit['objectID']}"
    external = hit.get("url") or ""
    return Item.make(
        source_type="hackernews",
        source_name="Hacker News",
        title=hit.get("title", ""),
        url=external or hn_url,
        external_url=hn_url,
        created_at=hit.get("created_at", ""),
        author=hit.get("author", ""),
        snippet=(hit.get("story_text") or "")[:400],
        engagement={"points": hit.get("points") or 0,
                    "comments": hit.get("num_comments") or 0},
        native_id=hit.get("objectID"),
    )


def fetch(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    cfg = sources.get("hackernews", {})
    if not cfg.get("enabled", True):
        return []
    items: list[Item] = []

    if cfg.get("front_page", True):
        resp = http.get(f"{API}/search", params={"tags": "front_page", "hitsPerPage": 60})
        items.extend(_to_item(h) for h in resp.json().get("hits", []))

    since = int(time.time()) - 24 * 3600
    min_points = cfg.get("min_points", 20)
    for query in keywords.get("hn_queries", []):
        resp = http.get(f"{API}/search_by_date", params={
            "query": query, "tags": "story",
            "numericFilters": f"created_at_i>{since},points>{min_points}",
            "hitsPerPage": 30,
        })
        items.extend(_to_item(h) for h in resp.json().get("hits", []))

    return items[: limit or None] if limit else items
