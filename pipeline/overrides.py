"""Admin overrides: pin / hide / tag, written by the admin console."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .schema import Item

log = logging.getLogger(__name__)


def load_overrides(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def apply_overrides(items: list[Item], overrides: dict) -> list[Item]:
    result = []
    for item in items:
        ov = overrides.get(item.id)
        if ov:
            if ov.get("hidden"):
                continue
            item.pinned = bool(ov.get("pinned"))
            item.tags = list(ov.get("tags", []))
        result.append(item)
    return result
