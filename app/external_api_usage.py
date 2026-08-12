from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.llm_usage import summarize_usage
from app.system_settings import get_system_value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _next_month_start(today: date | None = None) -> str:
    """Tavily resets credits on the first day of each month (docs FAQ)."""
    current = today or _utc_now().date()
    if current.month == 12:
        reset = date(current.year + 1, 1, 1)
    else:
        reset = date(current.year, current.month + 1, 1)
    return datetime(reset.year, reset.month, reset.day, tzinfo=timezone.utc).isoformat()


def _month_start(today: date | None = None) -> str:
    current = today or _utc_now().date()
    return datetime(current.year, current.month, 1, tzinfo=timezone.utc).isoformat()


def _pct(used: float | None, limit: float | None) -> float | None:
    if used is None or limit is None or limit <= 0:
        return None
    return round(min(100.0, max(0.0, (used / limit) * 100)), 1)


async def fetch_tavily_usage() -> dict[str, Any]:
    api_key = get_system_value("TAVILY_API_KEY")
    base_url = get_system_value("TAVILY_BASE_URL", "https://api.tavily.com").rstrip("/")
    if not api_key:
        return {
            "provider": "tavily",
            "configured": False,
            "ok": False,
            "error": "API key não configurada",
        }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{base_url}/usage",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.status_code == 401:
            return {
                "provider": "tavily",
                "configured": True,
                "ok": False,
                "error": "API key inválida ou sem permissão",
            }
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return {
            "provider": "tavily",
            "configured": True,
            "ok": False,
            "error": str(exc),
        }

    key = payload.get("key") if isinstance(payload.get("key"), dict) else {}
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    plan_limit = account.get("plan_limit")
    plan_usage = account.get("plan_usage")
    key_limit = key.get("limit")
    key_usage = key.get("usage")

    # Prefer account plan numbers for the main gauge; fall back to key limits.
    limit = plan_limit if plan_limit is not None else key_limit
    used = plan_usage if plan_usage is not None else key_usage
    remaining = None
    if limit is not None and used is not None:
        remaining = max(0, int(limit) - int(used))

    return {
        "provider": "tavily",
        "configured": True,
        "ok": True,
        "error": None,
        "plan_name": account.get("current_plan") or "—",
        "plan_limit": plan_limit,
        "plan_usage": plan_usage,
        "key_limit": key_limit,
        "key_usage": key_usage,
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "usage_pct": _pct(float(used) if used is not None else None, float(limit) if limit is not None else None),
        "period_start": _month_start(),
        "period_end": _next_month_start(),
        "reset_note": "Créditos Tavily resetam no 1º dia de cada mês (documentação oficial).",
        "includes": (
            f"{plan_limit} créditos / ciclo" if plan_limit is not None else "Limite do plano não informado pela API"
        ),
        "breakdown": {
            "search": account.get("search_usage", key.get("search_usage")),
            "extract": account.get("extract_usage", key.get("extract_usage")),
            "crawl": account.get("crawl_usage", key.get("crawl_usage")),
            "map": account.get("map_usage", key.get("map_usage")),
            "research": account.get("research_usage", key.get("research_usage")),
            "paygo_usage": account.get("paygo_usage"),
            "paygo_limit": account.get("paygo_limit"),
        },
        "raw": payload,
        "docs_url": "https://docs.tavily.com/documentation/api-reference/endpoint/usage",
    }


async def fetch_firecrawl_usage() -> dict[str, Any]:
    api_key = get_system_value("FIRECRAWL_API_KEY")
    base_url = get_system_value("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev").rstrip("/")
    if not api_key:
        return {
            "provider": "firecrawl",
            "configured": False,
            "ok": False,
            "error": "API key não configurada",
        }

    headers = {"Authorization": f"Bearer {api_key}"}
    last_error = None
    payload = None
    # Prefer v1 (snake_case + period fields widely documented); try v2 as fallback.
    for path in ("/v1/team/credit-usage", "/v2/team/credit-usage"):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(f"{base_url}{path}", headers=headers)
            if response.status_code == 401:
                return {
                    "provider": "firecrawl",
                    "configured": True,
                    "ok": False,
                    "error": "API key inválida ou sem permissão",
                }
            if response.status_code == 404:
                last_error = f"{path} não encontrado"
                continue
            response.raise_for_status()
            payload = response.json()
            break
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            payload = None

    if not isinstance(payload, dict):
        return {
            "provider": "firecrawl",
            "configured": True,
            "ok": False,
            "error": last_error or "Falha ao consultar crédito",
        }

    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    remaining = data.get("remaining_credits", data.get("remainingCredits"))
    plan_credits = data.get("plan_credits", data.get("planCredits"))
    period_start = data.get("billing_period_start", data.get("billingPeriodStart"))
    period_end = data.get("billing_period_end", data.get("billingPeriodEnd"))

    used = None
    if plan_credits is not None and remaining is not None:
        try:
            used = max(0, float(plan_credits) - float(remaining))
        except (TypeError, ValueError):
            used = None

    return {
        "provider": "firecrawl",
        "configured": True,
        "ok": True,
        "error": None,
        "plan_name": "Plano da team (Firecrawl)",
        "plan_limit": plan_credits,
        "plan_usage": used,
        "used": used,
        "limit": plan_credits,
        "remaining": remaining,
        "usage_pct": _pct(
            float(used) if used is not None else None,
            float(plan_credits) if plan_credits is not None else None,
        ),
        "period_start": period_start,
        "period_end": period_end,
        "reset_note": (
            f"Ciclo atual até {period_end}" if period_end else "Período de billing não informado (comum em plano free)."
        ),
        "includes": (
            f"{int(plan_credits)} créditos / ciclo de billing"
            if plan_credits is not None
            else "Allotment do plano não informado pela API"
        ),
        "breakdown": {},
        "raw": payload,
        "docs_url": "https://docs.firecrawl.dev/api-reference/endpoint/credit-usage",
    }


def _sorted_usage_rows(bucket: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten summarize_usage buckets into rows sorted by total tokens desc."""
    rows: list[dict[str, Any]] = []
    for name, stats in (bucket or {}).items():
        if not isinstance(stats, dict):
            continue
        row = {"name": name, **stats}
        rows.append(row)
    rows.sort(key=lambda r: (-int(r.get("total_tokens") or 0), str(r.get("name") or "")))
    return rows


def fetch_openai_usage() -> dict[str, Any]:
    """Local metering from Chat Completions usage (not OpenAI Billing Admin API)."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model = (os.getenv("OPENAI_MODEL") or "gpt-4.1").strip() or "gpt-4.1"
    default_provider = (os.getenv("LLM_PROVIDER") or "local").strip().lower()
    summary = summarize_usage()
    totals = summary.get("totals") or {}
    configured = bool(api_key)

    return {
        "provider": "openai",
        "kind": "llm_tokens",
        "configured": configured,
        "ok": True,
        "error": None if configured else "API key não configurada",
        "plan_name": f"Chat Completions · modelo default {model}",
        "includes": (
            "Tokens e custo estimado a partir das respostas `usage` "
            "(append-only em data/llm_usage.jsonl) — não é a Billing Admin API."
        ),
        "reset_note": (
            f"LLM_PROVIDER default: {default_provider}. "
            "Custo estimado via OPENAI_PRICE_*_PER_1M / tabela por modelo."
        ),
        "docs_url": "/api/llm/usage",
        "used": totals.get("total_tokens"),
        "limit": None,
        "remaining": None,
        "usage_pct": None,
        "period_start": None,
        "period_end": None,
        "totals": totals,
        "by_operation": _sorted_usage_rows(summary.get("by_operation") or {}),
        "by_model": _sorted_usage_rows(summary.get("by_model") or {}),
        "by_day": sorted(
            _sorted_usage_rows(summary.get("by_day") or {}),
            key=lambda r: str(r.get("name") or ""),
            reverse=True,
        ),
        "event_count": summary.get("event_count") or 0,
        "breakdown": {
            "prompt_tokens": totals.get("prompt_tokens"),
            "completion_tokens": totals.get("completion_tokens"),
            "total_tokens": totals.get("total_tokens"),
            "estimated_cost_usd": totals.get("estimated_cost_usd"),
            "calls": totals.get("calls"),
            "ok_calls": totals.get("ok_calls"),
        },
    }


async def fetch_all_external_api_usage() -> dict[str, Any]:
    tavily = await fetch_tavily_usage()
    firecrawl = await fetch_firecrawl_usage()
    openai = fetch_openai_usage()
    return {
        "fetched_at": _utc_now().isoformat(),
        "providers": [tavily, firecrawl, openai],
    }
