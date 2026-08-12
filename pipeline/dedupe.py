"""Seen-store filtering and cross-source merge of identical links."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .schema import Item, canonical_url, item_id

log = logging.getLogger(__name__)

SEEN_RETENTION_DAYS = 120


def load_seen(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(path: Path, seen: dict) -> None:
    cutoff = (datetime.now(tz=timezone.utc)
              - timedelta(days=SEEN_RETENTION_DAYS)).isoformat()
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    path.write_text(json.dumps(pruned, indent=0, sort_keys=True))


def _engagement_total(item: Item) -> int:
    return sum(v for v in item.engagement.values() if isinstance(v, (int, float)))


def dedupe(items: list[Item], seen: dict) -> list[Item]:
    """Drop already-seen items, then merge items sharing a canonical target URL.

    When a reddit/HN post links to the same article as an RSS entry, keep the
    highest-engagement copy and record the others in `also_on`.
    """
    fresh = [it for it in items if it.id not in seen]

    # Group by the canonical *target* — external_url when present, else url.
    groups: dict[str, list[Item]] = {}
    for it in fresh:
        target = canonical_url(it.external_url or it.url)
        key = item_id(target) if target else it.id
        groups.setdefault(key, []).append(it)

    merged: list[Item] = []
    for group in groups.values():
        group.sort(key=_engagement_total, reverse=True)
        primary = group[0]
        for other in group[1:]:
            note = {"source_name": other.source_name, "url": other.url,
                    "engagement": other.engagement}
            primary.also_on.append(note)
        merged.append(primary)

    log.info("dedupe: %d fetched, %d fresh, %d after merge",
             len(items), len(fresh), len(merged))
    return merged


def mark_seen(seen: dict, items: list[Item]) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    for it in items:
        seen.setdefault(it.id, now)
