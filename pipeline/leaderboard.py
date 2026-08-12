"""GitHub leaderboard: highest-starred LLM repos + fastest-growing ones.

"Fastest growing" blends two signals:
- star velocity for repos created in the last 14 days (stars / age)
- day-over-day star deltas from our own history for established repos,
  which sharpens after the tracker has run for a couple of days
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import http

log = logging.getLogger(__name__)

API = "https://api.github.com/search/repositories"
TOP_QUERY = 'llm OR "large language model" OR "llm inference"'
NEW_QUERY = 'llm OR gguf OR "language model" OR "inference engine"'
HISTORY_DAYS = 30
BOARD_SIZE = 12


def load_history(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_history(path: Path, history: dict) -> None:
    path.write_text(json.dumps(history, indent=0, sort_keys=True))


def velocity(created_at: str, stars: int, now: datetime) -> int:
    """Stars per day since creation."""
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return round(stars / max((now - created).days, 1))


def tracked_delta(history: dict, name: str, current: int, today: str) -> int | None:
    """Stars per day since the oldest history sample; None until 2 samples exist."""
    samples = history.get(name, {})
    days = sorted(d for d in samples if d < today)
    if not days:
        return None
    first = days[0]
    span = max((date.fromisoformat(today) - date.fromisoformat(first)).days, 1)
    return round((current - samples[first]) / span)


def _entry(repo: dict, delta: int | None) -> dict:
    return {
        "name": repo["full_name"],
        "url": repo["html_url"],
        "description": (repo.get("description") or "")[:160],
        "stars": repo.get("stargazers_count", 0),
        "delta_per_day": delta,
    }


def watch(history: dict, repos: list[str]) -> list[dict]:
    """Always-tracked repos: direct lookups (no search quota), sorted by stars."""
    now = datetime.now(tz=timezone.utc)
    today = now.date().isoformat()
    entries = []
    for name in repos:
        try:
            repo = http.get(f"https://api.github.com/repos/{name}",
                            headers=http.github_headers()).json()
        except Exception as exc:  # noqa: BLE001 — a renamed/deleted repo must not kill the board
            log.warning("watchlist repo failed %s: %s", name, exc)
            continue
        delta = tracked_delta(history, repo["full_name"], repo["stargazers_count"], today)
        entries.append(_entry(repo, delta))
        history.setdefault(repo["full_name"], {})[today] = repo["stargazers_count"]
    entries.sort(key=lambda e: e["stars"], reverse=True)
    return entries


def build(history: dict, watch_repos: list[str] | None = None) -> dict:
    now = datetime.now(tz=timezone.utc)
    today = now.date().isoformat()

    top_repos = http.get(API, headers=http.github_headers(), params={
        "q": TOP_QUERY, "sort": "stars", "order": "desc", "per_page": 25,
    }).json().get("items", [])

    since = (now - timedelta(days=14)).date().isoformat()
    new_repos = http.get(API, headers=http.github_headers(), params={
        "q": f"{NEW_QUERY} created:>{since} stars:>50",
        "sort": "stars", "order": "desc", "per_page": 30,
    }).json().get("items", [])

    # compute deltas BEFORE recording today's sample (else span collapses to 0)
    top = [_entry(r, tracked_delta(history, r["full_name"], r["stargazers_count"], today))
           for r in top_repos[:BOARD_SIZE]]

    rising: dict[str, dict] = {}
    for repo in new_repos:
        rising[repo["full_name"]] = _entry(
            repo, velocity(repo["created_at"], repo["stargazers_count"], now))
    for repo in top_repos:  # established repos with measured day-over-day growth
        delta = tracked_delta(history, repo["full_name"], repo["stargazers_count"], today)
        if delta and delta > 0:
            existing = rising.get(repo["full_name"])
            if not existing or (existing["delta_per_day"] or 0) < delta:
                rising[repo["full_name"]] = _entry(repo, delta)
    rising_list = sorted(rising.values(),
                         key=lambda e: e["delta_per_day"] or 0, reverse=True)[:BOARD_SIZE]

    # record today's samples and prune old ones
    for repo in top_repos + new_repos:
        history.setdefault(repo["full_name"], {})[today] = repo["stargazers_count"]
    cutoff = (now - timedelta(days=HISTORY_DAYS)).date().isoformat()
    for name in list(history):
        history[name] = {d: s for d, s in history[name].items() if d >= cutoff}
        if not history[name]:
            del history[name]

    watched = watch(history, watch_repos or [])
    log.info("leaderboard: %d top, %d rising, %d watched, %d repos tracked",
             len(top), len(rising_list), len(watched), len(history))
    return {"top": top, "rising": rising_list, "watch": watched}
