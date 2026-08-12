"""Influencer posts via the public Bluesky AppView API (no auth)."""

from __future__ import annotations

import logging

from .. import http
from ..schema import Item

log = logging.getLogger(__name__)

API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"


def fetch(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    include = [k.lower() for k in keywords.get("include", [])]
    items: list[Item] = []
    for acct in sources.get("bluesky", []):
        if not acct.get("enabled", True):
            continue
        handle = acct["handle"]
        try:
            resp = http.get(API, params={"actor": handle, "limit": 30,
                                         "filter": "posts_no_replies"})
        except Exception as exc:  # noqa: BLE001 — handles change/deactivate; not fatal
            log.warning("bluesky failed for %s: %s", handle, exc)
            continue
        for entry in resp.json().get("feed", []):
            post = entry.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "")
            embed = record.get("embed", {})
            external = embed.get("external", {}).get("uri", "") if isinstance(embed, dict) else ""
            # keep only posts that link somewhere or hit a keyword
            if not external and not any(k in text.lower() for k in include):
                continue
            uri = post.get("uri", "")  # at://did/app.bsky.feed.post/rkey
            rkey = uri.rsplit("/", 1)[-1] if uri else ""
            items.append(Item.make(
                source_type="bluesky",
                source_name=f"@{handle}",
                title=text[:200] or "(link post)",
                url=f"https://bsky.app/profile/{handle}/post/{rkey}",
                external_url=external,
                created_at=record.get("createdAt", ""),
                author=handle,
                snippet=text[:400],
                engagement={"likes": post.get("likeCount", 0) or 0,
                            "comments": post.get("replyCount", 0) or 0},
                native_id=uri,
            ))
    return items[: limit or None] if limit else items
