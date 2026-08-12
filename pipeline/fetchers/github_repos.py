"""New trending repos via the GitHub search API (authenticated in Actions)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .. import http
from ..schema import Item

log = logging.getLogger(__name__)

API = "https://api.github.com/search/repositories"


def fetch(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    cfg = sources.get("github_search", {})
    if not cfg.get("enabled", True):
        return []
    days = cfg.get("created_within_days", 7)
    min_stars = cfg.get("min_stars", 30)
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()

    items: list[Item] = []
    for query in cfg.get("queries", [])[:4]:  # secondary rate limits: keep it small
        q = f"{query} created:>{since} stars:>{min_stars}"
        resp = http.get(API, headers=http.github_headers(),
                        params={"q": q, "sort": "stars", "order": "desc", "per_page": 50})
        for repo in resp.json().get("items", []):
            items.append(Item.make(
                source_type="github_repo",
                source_name="GitHub trending",
                title=f"{repo['full_name']} — {repo.get('description') or 'new repository'}",
                url=repo["html_url"],
                created_at=repo.get("created_at", ""),
                author=repo.get("owner", {}).get("login", ""),
                snippet=(repo.get("description") or "")[:400],
                engagement={"stars": repo.get("stargazers_count", 0)},
                native_id=str(repo.get("id")),
            ))
    return items[: limit or None] if limit else items
