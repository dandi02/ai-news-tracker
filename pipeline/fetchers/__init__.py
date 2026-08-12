"""Fetcher registry: maps a source key from sources.yaml to a fetch function.

Every fetcher has the signature  fetch(sources_cfg, keywords_cfg, limit) -> list[Item]
and is allowed to raise — the orchestrator isolates failures per source.
"""

from . import bluesky, github_releases, github_repos, hackernews, huggingface, reddit, rss

REGISTRY = {
    "rss": rss.fetch,
    "youtube": rss.fetch_youtube,
    "hackernews": hackernews.fetch,
    "reddit": reddit.fetch,
    "github_releases": github_releases.fetch,
    "github_repos": github_repos.fetch,
    "huggingface": huggingface.fetch,
    "bluesky": bluesky.fetch,
}
