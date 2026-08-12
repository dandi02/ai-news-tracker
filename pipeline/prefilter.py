"""Keyword + engagement prefilter that caps how many items reach the LLM."""

from __future__ import annotations

import logging

from .schema import Item

log = logging.getLogger(__name__)

MAX_LLM_ITEMS = 150

# An item with no keyword hit still passes if it clears its source's bar.
ENGAGEMENT_THRESHOLDS = {
    "reddit": ("points", 100),
    "hackernews": ("points", 80),
    "github_repo": ("stars", 100),
    "github_release": ("stars", 0),   # watchlist releases always matter
    "hf_model": ("likes", 20),
    "hf_paper": ("likes", 10),
    "bluesky": ("likes", 30),
}


def _keyword_hit(item: Item, include: list[str]) -> bool:
    haystack = f"{item.title} {item.snippet}".lower()
    return any(k in haystack for k in include)


def _excluded(item: Item, exclude: list[str]) -> bool:
    haystack = f"{item.title} {item.snippet}".lower()
    return any(k in haystack for k in exclude)


def _clears_bar(item: Item) -> bool:
    metric, bar = ENGAGEMENT_THRESHOLDS.get(item.source_type, ("points", 10**9))
    return item.engagement.get(metric, 0) >= bar


def _engagement_total(item: Item) -> int:
    return sum(v for v in item.engagement.values() if isinstance(v, (int, float)))


def prefilter(items: list[Item], keywords: dict) -> list[Item]:
    include = [k.lower() for k in keywords.get("include", [])]
    exclude = [k.lower() for k in keywords.get("exclude", [])]

    kept = [
        it for it in items
        if not _excluded(it, exclude)
        and (_keyword_hit(it, include) or _clears_bar(it)
             or it.source_type in ("rss", "youtube", "github_release"))
    ]
    kept.sort(key=_engagement_total, reverse=True)
    if len(kept) > MAX_LLM_ITEMS:
        log.info("prefilter: capping %d items to %d", len(kept), MAX_LLM_ITEMS)
        kept = kept[:MAX_LLM_ITEMS]
    log.info("prefilter: %d in, %d out", len(items), len(kept))
    return kept
