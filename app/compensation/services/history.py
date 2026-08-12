from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.compensation.core import DATA_DIR


CACHE_DIR = DATA_DIR / "compensation_cache"


def list_cached_research() -> list[dict[str, Any]]:
    if not CACHE_DIR.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in CACHE_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        profile = payload.get("profile") or {}
        market = payload.get("market") or {}
        sample = payload.get("sample") or {}
        confidence = payload.get("confidence") or {}
        providers = payload.get("providers") or {}
        recommended = market.get("recommended_range") or {}
        items.append(
            {
                "cache_key": path.stem,
                "research_id": payload.get("research_id") or path.stem,
                "normalized_role": profile.get("normalized_role") or "",
                "seniority": profile.get("seniority") or "",
                "contract_type": market.get("contract_type") or "",
                "unit": market.get("unit") or "",
                "median": market.get("median"),
                "recommended_min": recommended.get("min"),
                "recommended_max": recommended.get("max"),
                "observations": sample.get("observations") or 0,
                "sources": sample.get("sources") or 0,
                "confidence_level": confidence.get("level") or "LOW",
                "confidence_score": confidence.get("score") or 0,
                "search_engines_used": providers.get("search_engines_used") or [],
                "crawlers_used": providers.get("crawlers_used") or [],
                "created_at": payload.get("created_at") or "",
                "updated_at": path.stat().st_mtime,
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items


def load_cached_research(cache_key: str) -> dict[str, Any] | None:
    key = Path(cache_key).name.replace(".json", "")
    path = CACHE_DIR / f"{key}.json"
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_latest_cached_research() -> dict[str, Any] | None:
    items = list_cached_research()
    if not items:
        return None
    return load_cached_research(items[0]["cache_key"])
