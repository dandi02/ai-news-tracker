"""Normalized item schema and URL/id canonicalization."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING_PARAMS = re.compile(r"^(utm_|ref_|fbclid|gclid|mc_cid|mc_eid)")


def canonical_url(url: str) -> str:
    """Normalize a URL so the same link from different sources hashes identically."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = "https"  # scheme never distinguishes two copies of the same link
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)]
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def item_id(url: str, native_id: str | None = None) -> str:
    """Stable id: sha1 of the canonical URL (or a source-native id if no URL)."""
    basis = canonical_url(url) or f"native:{native_id}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


@dataclass
class Item:
    id: str
    source_type: str   # reddit | github_repo | github_release | hf_model | hf_paper | hackernews | rss | youtube | bluesky
    source_name: str
    title: str
    url: str
    created_at: str    # ISO 8601
    external_url: str = ""
    author: str = ""
    snippet: str = ""
    engagement: dict = field(default_factory=dict)  # points/comments/stars/downloads/likes

    # Filled in by later pipeline stages:
    also_on: list = field(default_factory=list)     # cross-source co-occurrences
    keep: bool = True
    summary: str = ""
    importance: int = 0
    category: str = "discussion"
    group_key: str = ""
    curated: bool = False                            # True when Claude scored it
    pinned: bool = False
    tags: list = field(default_factory=list)

    @classmethod
    def make(cls, *, source_type: str, source_name: str, title: str, url: str,
             created_at: str, native_id: str | None = None, **kw) -> "Item":
        return cls(
            id=item_id(url, native_id),
            source_type=source_type,
            source_name=source_name,
            title=(title or "").strip()[:300],
            url=url,
            created_at=created_at,
            **kw,
        )

    def to_dict(self) -> dict:
        return asdict(self)
