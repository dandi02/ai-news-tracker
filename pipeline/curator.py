"""Claude-based curation with a keyword-scoring fallback.

One batched call per ~60 items: Claude decides keep/drop, writes a 1-2 sentence
summary, scores importance 1-10, categorizes, and assigns a group_key so
cross-source coverage of the same story can be folded together.
"""

from __future__ import annotations

import json
import logging

from .schema import Item

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
CHUNK_SIZE = 60
MAX_TOKENS = 16000

CATEGORIES = ["new-model-release", "tooling", "research", "fine-tune", "dataset", "discussion"]

SYSTEM_PROMPT = """You curate a daily news feed for SQP, a software development team \
tracking open-source LLMs. Given raw items scraped from GitHub, Hugging Face, Reddit, \
Hacker News, blogs, YouTube, and Bluesky, decide for each item whether it belongs in \
the feed, and score it.

Keep: new open-weight model releases, significant fine-tunes or quantized variants, \
inference/serving/training tooling, important research and benchmarks, datasets, and \
high-signal discussions about running LLMs locally or in production.
Drop (keep=false): memes, support questions ("which GPU should I buy"), hiring posts, \
vague hype with no substance, closed-model marketing with no open-source relevance, \
and duplicate low-value coverage.

Scoring rubric (importance):
- 9-10: major new open-weight model family release (e.g. a new Llama/Qwen/DeepSeek generation)
- 7-8: notable model release, major tooling version, influential research result
- 5-6: solid tooling release, useful benchmark, meaningful ecosystem news
- 2-4: single fine-tune or quant, minor tool update, ordinary discussion
- 1: barely relevant

Summary: 1-2 factual sentences. State what it is and why a developer would care. \
No hype, no "this is exciting".

group_key: items covering the SAME story must share the same short slug \
(e.g. "qwen3-coder-release"). Unrelated items get unique slugs.

Return a result for EVERY input item, matched by id."""


def _output_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "keep": {"type": "boolean"},
                        "summary": {"type": "string"},
                        "importance": {"type": "integer", "enum": list(range(1, 11))},
                        "category": {"type": "string", "enum": CATEGORIES},
                        "group_key": {"type": "string"},
                    },
                    "required": ["id", "keep", "summary", "importance", "category", "group_key"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def _compact(item: Item) -> dict:
    return {
        "id": item.id,
        "src": f"{item.source_type}/{item.source_name}",
        "title": item.title,
        "snippet": item.snippet[:300],
        "engagement": {k: v for k, v in item.engagement.items() if v},
    }


def _curate_chunk(client, items: list[Item]) -> dict[str, dict]:
    payload = json.dumps([_compact(it) for it in items], ensure_ascii=False)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},  # calls 2+ read the rubric from cache
        }],
        output_config={"format": {"type": "json_schema", "schema": _output_schema()}},
        messages=[{"role": "user", "content": f"Today's raw items:\n{payload}"}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    results = json.loads(text)["items"]
    log.info("curated %d items (%d in / %d out tokens)",
             len(results), response.usage.input_tokens, response.usage.output_tokens)
    return {r["id"]: r for r in results}


def curate(items: list[Item]) -> list[Item]:
    """Score items with Claude; on any failure fall back to keyword scoring."""
    if not items:
        return items

    import anthropic
    # credentials resolve from ANTHROPIC_API_KEY or an `ant auth login` profile;
    # if neither exists the first call raises and run.py falls back to keywords
    client = anthropic.Anthropic()

    verdicts: dict[str, dict] = {}
    for start in range(0, len(items), CHUNK_SIZE):
        chunk = items[start:start + CHUNK_SIZE]
        verdicts.update(_curate_chunk(client, chunk))

    for item in items:
        verdict = verdicts.get(item.id)
        if verdict is None:  # model skipped it despite instructions — keep unscored
            item.curated = False
            continue
        item.keep = verdict["keep"]
        item.summary = verdict["summary"]
        item.importance = verdict["importance"]
        item.category = verdict["category"]
        item.group_key = verdict["group_key"]
        item.curated = True
    return items


def fallback_score(items: list[Item], keywords: dict) -> list[Item]:
    """Keyword + engagement scoring used when the Claude call is unavailable."""
    cfg = keywords.get("fallback", {})
    weights = cfg.get("engagement_weights", {})
    include = [k.lower() for k in keywords.get("include", [])]
    hints = cfg.get("category_hints", {})

    for item in items:
        score = float(cfg.get("base_score", 2))
        for metric, value in item.engagement.items():
            w = weights.get(metric)
            if w and isinstance(value, (int, float)):
                score += min(w.get("cap", 3), value / max(w.get("divisor", 100), 1))
        haystack = f"{item.title} {item.snippet}".lower()
        if any(k in haystack for k in include):
            score += cfg.get("keyword_hit_bonus", 1)

        item.importance = max(1, min(10, round(score)))
        item.keep = True
        item.summary = item.snippet[:200] or item.title
        item.group_key = item.id
        item.category = "discussion"
        for category, terms in hints.items():
            if any(t in haystack for t in terms):
                item.category = category
                break
        item.curated = False
    return items


def fold_groups(items: list[Item]) -> list[Item]:
    """Collapse items sharing a group_key: keep the top one, fold the rest into also_on."""
    kept = [it for it in items if it.keep]
    groups: dict[str, list[Item]] = {}
    for it in kept:
        groups.setdefault(it.group_key or it.id, []).append(it)

    result: list[Item] = []
    for group in groups.values():
        group.sort(key=lambda i: (i.importance, sum(
            v for v in i.engagement.values() if isinstance(v, (int, float)))), reverse=True)
        primary = group[0]
        for other in group[1:]:
            primary.also_on.append({"source_name": other.source_name, "url": other.url,
                                    "engagement": other.engagement})
        result.append(primary)
    result.sort(key=lambda i: i.importance, reverse=True)
    return result
