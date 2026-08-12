"""Shared HTTP session: descriptive UA, timeouts, retries, conditional requests."""

from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

USER_AGENT = "sqp-llm-tracker/1.0 (open-source LLM news aggregator; contact: danidin@gmail.com)"
TIMEOUT = 20
RETRIES = 2

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT

# ETag/Last-Modified cache: {url: {"etag": ..., "last_modified": ..., "body": ...}}
_cache: dict = {}
_cache_path: Path | None = None


def load_cache(path: Path) -> None:
    global _cache, _cache_path
    _cache_path = path
    try:
        _cache = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        _cache = {}


def save_cache() -> None:
    if _cache_path is not None:
        _cache_path.write_text(json.dumps(_cache))


def get(url: str, *, headers: dict | None = None, conditional: bool = False,
        params: dict | None = None) -> requests.Response | None:
    """GET with retries. With conditional=True, replays ETag/Last-Modified and
    returns the cached body on 304 (as a synthetic response). Returns None only
    when the cached copy is unavailable on 304 (treat as 'no change')."""
    hdrs = dict(headers or {})
    entry = _cache.get(url, {}) if conditional else {}
    if entry.get("etag"):
        hdrs["If-None-Match"] = entry["etag"]
    if entry.get("last_modified"):
        hdrs["If-Modified-Since"] = entry["last_modified"]

    last_exc: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            resp = _session.get(url, headers=hdrs, params=params, timeout=TIMEOUT)
            if resp.status_code == 304:
                log.info("304 not modified: %s", url)
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} from {url}", response=resp)
            resp.raise_for_status()
            if conditional:
                _cache[url] = {
                    "etag": resp.headers.get("ETag", ""),
                    "last_modified": resp.headers.get("Last-Modified", ""),
                }
            return resp
        except Exception as exc:  # noqa: BLE001 — every failure is retried the same way
            last_exc = exc
            if attempt < RETRIES:
                retry_after = 0.0
                resp = getattr(exc, "response", None)
                if resp is not None and resp.headers.get("Retry-After", "").isdigit():
                    retry_after = float(resp.headers["Retry-After"])
                time.sleep(max(retry_after, 2 ** attempt + random.random()))
    raise last_exc  # type: ignore[misc]


def github_headers() -> dict:
    hdrs = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    return hdrs
