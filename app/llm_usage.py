from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.compensation.core import append_jsonl


DATA_DIR = Path("data")
USAGE_LOG_PATH = DATA_DIR / "llm_usage.jsonl"

# USD per 1M tokens. Env overrides apply as default for unknown models / gpt-4.1 baseline.
DEFAULT_MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def price_for_model(model: str) -> tuple[float, float]:
    """Return (input_per_1m, output_per_1m) USD."""
    key = (model or "").strip().lower()
    env_in = _env_float("OPENAI_PRICE_INPUT_PER_1M", 2.00)
    env_out = _env_float("OPENAI_PRICE_OUTPUT_PER_1M", 8.00)
    if key in DEFAULT_MODEL_PRICES:
        table_in, table_out = DEFAULT_MODEL_PRICES[key]
        # Env overrides the table defaults when set (same vars as gpt-4.1 baseline).
        if os.getenv("OPENAI_PRICE_INPUT_PER_1M"):
            table_in = env_in
        if os.getenv("OPENAI_PRICE_OUTPUT_PER_1M"):
            table_out = env_out
        return table_in, table_out
    return env_in, env_out


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_per_1m, output_per_1m = price_for_model(model)
    cost = (max(0, prompt_tokens) / 1_000_000.0) * input_per_1m + (
        max(0, completion_tokens) / 1_000_000.0
    ) * output_per_1m
    return round(cost, 8)


def record_usage_event(
    *,
    provider: str,
    model: str,
    operation: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    estimated_cost_usd: float | None = None,
    attempts: int = 1,
    ok: bool = True,
    job_id: str | None = None,
    candidate_id: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    if estimated_cost_usd is None:
        estimated_cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)
    if total_tokens <= 0:
        total_tokens = max(0, prompt_tokens) + max(0, completion_tokens)
    event = {
        "ts": _utc_now_iso(),
        "provider": provider,
        "model": model,
        "operation": operation or "unknown",
        "job_id": job_id or "",
        "candidate_id": candidate_id or "",
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "estimated_cost_usd": float(estimated_cost_usd or 0.0),
        "attempts": int(attempts or 1),
        "ok": bool(ok),
    }
    append_jsonl(path or USAGE_LOG_PATH, event)
    return event


def usage_from_audit_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return empty_usage()
    prompt = int(payload.get("prompt_tokens") or 0)
    completion = int(payload.get("completion_tokens") or 0)
    total = int(payload.get("total_tokens") or (prompt + completion))
    cost = payload.get("estimated_cost_usd")
    try:
        cost_f = float(cost) if cost is not None else 0.0
    except (TypeError, ValueError):
        cost_f = 0.0
    calls = 1 if (prompt or completion or total) else 0
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "estimated_cost_usd": round(cost_f, 8),
        "calls": calls,
    }


def empty_usage() -> dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "calls": 0,
    }


def aggregate_usage(*parts: dict[str, Any] | None) -> dict[str, Any]:
    total = empty_usage()
    for part in parts:
        if not isinstance(part, dict):
            continue
        total["prompt_tokens"] += int(part.get("prompt_tokens") or 0)
        total["completion_tokens"] += int(part.get("completion_tokens") or 0)
        total["total_tokens"] += int(part.get("total_tokens") or 0)
        try:
            total["estimated_cost_usd"] += float(part.get("estimated_cost_usd") or 0.0)
        except (TypeError, ValueError):
            pass
        total["calls"] += int(part.get("calls") or 0)
    total["estimated_cost_usd"] = round(float(total["estimated_cost_usd"]), 8)
    return total


def aggregate_usage_from_audits(audits: list[Any] | None) -> dict[str, Any]:
    if not audits:
        return empty_usage()
    parts = [usage_from_audit_payload(item if isinstance(item, dict) else None) for item in audits]
    return aggregate_usage(*parts)


def read_usage_events(path: Path | None = None, *, since: str | None = None) -> list[dict[str, Any]]:
    file_path = path or USAGE_LOG_PATH
    if not file_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if since and str(item.get("ts") or "") < since:
                continue
            events.append(item)
    return events


def summarize_usage(since: str | None = None, *, path: Path | None = None) -> dict[str, Any]:
    events = read_usage_events(path, since=since)
    by_day: dict[str, dict[str, Any]] = {}
    by_operation: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}

    def _bump(bucket: dict[str, dict[str, Any]], key: str, event: dict[str, Any]) -> None:
        row = bucket.setdefault(
            key,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "calls": 0,
                "ok_calls": 0,
            },
        )
        row["prompt_tokens"] += int(event.get("prompt_tokens") or 0)
        row["completion_tokens"] += int(event.get("completion_tokens") or 0)
        row["total_tokens"] += int(event.get("total_tokens") or 0)
        row["estimated_cost_usd"] = round(
            float(row["estimated_cost_usd"]) + float(event.get("estimated_cost_usd") or 0.0),
            8,
        )
        row["calls"] += 1
        if event.get("ok"):
            row["ok_calls"] += 1

    totals = empty_usage()
    totals["ok_calls"] = 0
    for event in events:
        ts = str(event.get("ts") or "")
        day = ts[:10] if len(ts) >= 10 else "unknown"
        _bump(by_day, day, event)
        _bump(by_operation, str(event.get("operation") or "unknown"), event)
        _bump(by_model, str(event.get("model") or "unknown"), event)
        totals["prompt_tokens"] += int(event.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(event.get("completion_tokens") or 0)
        totals["total_tokens"] += int(event.get("total_tokens") or 0)
        totals["estimated_cost_usd"] = round(
            float(totals["estimated_cost_usd"]) + float(event.get("estimated_cost_usd") or 0.0),
            8,
        )
        totals["calls"] += 1
        if event.get("ok"):
            totals["ok_calls"] += 1

    return {
        "since": since,
        "event_count": len(events),
        "totals": totals,
        "by_day": by_day,
        "by_operation": by_operation,
        "by_model": by_model,
        "recent": events[-20:],
    }
