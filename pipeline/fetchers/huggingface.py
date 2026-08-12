"""Hugging Face Hub: new + trending text-generation models, and daily papers."""

from __future__ import annotations

import logging

from .. import http
from ..schema import Item

log = logging.getLogger(__name__)

API = "https://huggingface.co/api"


def _model_item(model: dict, label: str) -> Item | None:
    mid = model.get("id") or model.get("modelId")
    if not mid:
        return None
    return Item.make(
        source_type="hf_model",
        source_name=f"HF {label}",
        title=mid,
        url=f"https://huggingface.co/{mid}",
        created_at=model.get("createdAt", "") or model.get("lastModified", ""),
        author=mid.split("/")[0] if "/" in mid else "",
        snippet=", ".join(model.get("tags", [])[:12]),
        engagement={"likes": model.get("likes", 0) or 0,
                    "downloads": model.get("downloads", 0) or 0},
        native_id=mid,
    )


def fetch(sources: dict, keywords: dict, limit: int = 0) -> list[Item]:
    cfg = sources.get("huggingface", {})
    if not cfg.get("enabled", True):
        return []
    items: list[Item] = []

    queries = [
        ({"pipeline_tag": "text-generation", "sort": "createdAt", "direction": -1,
          "limit": cfg.get("models_limit", 50)}, "new models"),
        ({"pipeline_tag": "text-generation", "sort": "trendingScore", "direction": -1,
          "limit": cfg.get("trending_limit", 30)}, "trending"),
    ]
    for params, label in queries:
        try:
            for model in http.get(f"{API}/models", params=params).json():
                item = _model_item(model, label)
                if item:
                    items.append(item)
        except Exception as exc:  # noqa: BLE001 — sort params are undocumented, tolerate drift
            log.warning("HF models query failed (%s): %s", label, exc)

    if cfg.get("daily_papers", True):
        try:
            for entry in http.get(f"{API}/daily_papers").json():
                paper = entry.get("paper", {})
                pid = paper.get("id", "")
                if not pid:
                    continue
                items.append(Item.make(
                    source_type="hf_paper",
                    source_name="HF daily papers",
                    title=paper.get("title", ""),
                    url=f"https://huggingface.co/papers/{pid}",
                    created_at=entry.get("publishedAt", "") or paper.get("publishedAt", ""),
                    snippet=(paper.get("summary") or "")[:400],
                    engagement={"likes": paper.get("upvotes", 0) or 0},
                    native_id=pid,
                ))
        except Exception as exc:  # noqa: BLE001
            log.warning("HF daily papers failed: %s", exc)

    return items[: limit or None] if limit else items
