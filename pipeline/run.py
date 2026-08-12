"""Pipeline orchestrator.

Usage:
    python -m pipeline.run                 # full run (needs ANTHROPIC_API_KEY)
    python -m pipeline.run --dry-run       # write to build-preview/, don't touch state
    python -m pipeline.run --no-llm        # skip Claude, keyword fallback scoring
    python -m pipeline.run --limit 10      # cap items per source (fast local runs)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import curator, dedupe, http, leaderboard, overrides as overrides_mod, prefilter, render
from .fetchers import REGISTRY

log = logging.getLogger("pipeline")

ROOT = Path(__file__).resolve().parent.parent


def site_url() -> str:
    """Pages URL, derived from the Actions environment when available."""
    import os
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return "https://example.github.io/ai-news-tracker/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQP AI news tracker pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="write outputs to build-preview/, leave state untouched")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip the Claude call and use keyword fallback scoring")
    parser.add_argument("--limit", type=int, default=0,
                        help="cap items per source (for fast local runs)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    data_dir = ROOT / "data"
    out_root = (ROOT / "build-preview") if args.dry_run else ROOT
    days_dir = out_root / "data" / "days"
    site_data = out_root / "site" / "data"

    sources = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())
    keywords = yaml.safe_load((ROOT / "config" / "keywords.yaml").read_text())

    http.load_cache(data_dir / "http_cache.json")
    seen = dedupe.load_seen(data_dir / "seen.json")
    ov = overrides_mod.load_overrides(data_dir / "overrides.json")

    # ---- fetch (per-source isolation) ----
    items = []
    sources_status: dict = {}
    for name, fetch in REGISTRY.items():
        try:
            got = fetch(sources, keywords, args.limit)
            items.extend(got)
            sources_status[name] = {"ok": True, "count": len(got)}
            log.info("%s: %d items", name, len(got))
        except Exception as exc:  # noqa: BLE001 — one source must never kill the run
            sources_status[name] = {"ok": False, "error": str(exc)[:300]}
            log.error("%s FAILED: %s", name, exc)

    if not any(s["ok"] for s in sources_status.values()):
        log.error("every fetcher failed — keeping yesterday's feed, exiting nonzero")
        return 1

    # ---- github leaderboard (non-fatal) ----
    star_history = leaderboard.load_history(data_dir / "star_history.json")
    boards = None
    watch_repos = [w["repo"] for w in sources.get("github_watchlist", [])
                   if w.get("enabled", True)]
    try:
        boards = leaderboard.build(star_history, watch_repos)
        sources_status["github_leaderboard"] = {
            "ok": True, "count": len(boards["top"]) + len(boards["rising"])}
    except Exception as exc:  # noqa: BLE001 — the boards are a bonus, never fatal
        sources_status["github_leaderboard"] = {"ok": False, "error": str(exc)[:300]}
        log.error("github leaderboard FAILED: %s", exc)

    # ---- dedupe + prefilter ----
    items = dedupe.dedupe(items, seen)
    items = prefilter.prefilter(items, keywords)

    # ---- curate ----
    llm_ok = False
    if not args.no_llm:
        try:
            items = curator.curate(items)
            llm_ok = True
        except Exception as exc:  # noqa: BLE001 — the feed must ship regardless
            log.error("Claude curation failed (%s) — using keyword fallback", exc)
    if not llm_ok:
        items = curator.fallback_score(items, keywords)
    kept = curator.fold_groups(items)
    log.info("curation: %d kept of %d (llm=%s)", len(kept), len(items), llm_ok)

    # ---- overrides + render ----
    kept = overrides_mod.apply_overrides(kept, ov)
    day = datetime.now(tz=timezone.utc).date().isoformat()
    render.write_day_archive(days_dir, day, [it.to_dict() for it in kept], sources_status)
    # merge real archive history with today's output when previewing
    if args.dry_run:
        real_days = data_dir / "days"
        for f in real_days.glob("*.json") if real_days.exists() else []:
            target = days_dir / f.name
            if not target.exists():
                target.write_text(f.read_text())
    feed = render.build_feed_json(days_dir, site_data / "feed.json", ov,
                                  extra={"github_leaderboard": boards} if boards else None)
    render.build_rss(feed, out_root / "site" / "feed.xml", site_url())

    # ---- save state ----
    if not args.dry_run:
        # mark everything that was evaluated (kept or dropped) so it isn't re-curated
        dedupe.mark_seen(seen, items)
        dedupe.save_seen(data_dir / "seen.json", seen)
        leaderboard.save_history(data_dir / "star_history.json", star_history)
        http.save_cache()

    log.info("done: %d items published for %s -> %s", len(kept), day,
             site_data / "feed.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
