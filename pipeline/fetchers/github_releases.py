"""Releases from a watchlist of repos, via public releases.atom (no API quota)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..schema import Item
from . import rss as rss_mod

log = logging.getLogger(__name__)

MAX_AGE_DAYS = 3  # only surface releases from the last few days


def fetch(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    items: list[Item] = []
    for entry in sources.get("github_releases", []):
        if not entry.get("enabled", True):
            continue
        repo = entry["repo"]
        url = f"https://github.com/{repo}/releases.atom"
        try:
            got = rss_mod._parse_feed(url, repo, "github_release", keywords)
        except Exception as exc:  # noqa: BLE001 — one repo must not kill the watchlist
            log.warning("releases feed failed for %s: %s", repo, exc)
            continue
        for item in got:
            try:
                created = datetime.fromisoformat(item.created_at)
            except ValueError:
                continue
            if created >= cutoff:
                item.title = f"{repo}: {item.title}"
                items.append(item)
    return items[: limit or None] if limit else items
