from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path("config")
DATA_DIR = Path("data")


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    enabled: bool = False
    priority: int = 100
    timeout_seconds: int = 10
    max_results: int = 5
    retry_count: int = 1


@dataclass(frozen=True)
class CompensationSettings:
    ollama_base_url: str
    ollama_model: str
    search_engines: list[str]
    enabled_crawlers: list[str]
    clt_to_pj_factor: float
    work_hours_month: int
    max_parallel_searches: int
    max_parallel_crawls: int
    cache_ttl_days: int
    http_timeout_seconds: int
    playwright_timeout_seconds: int
    research_timeout_seconds: int
    app_api_key: str


def get_settings() -> CompensationSettings:
    pricing = _business_pricing()
    from app.system_settings import get_system_value

    ollama_url = get_system_value("OLLAMA_BASE_URL") or os.getenv("OLLAMA_BASE_URL") or os.getenv(
        "LOCAL_LLM_URL", "http://gpu-server-01:11434"
    )
    ollama_model = get_system_value("OLLAMA_MODEL") or os.getenv("OLLAMA_MODEL") or os.getenv(
        "LOCAL_LLM_MODEL", "qwen2.5:14b"
    )
    return CompensationSettings(
        ollama_base_url=ollama_url,
        ollama_model=ollama_model,
        search_engines=_split_env("SEARCH_ENGINES", "tavily"),
        enabled_crawlers=_split_env("ENABLED_CRAWLERS", "glassdoor,indeed,vagas,generic"),
        clt_to_pj_factor=float(pricing.get("clt_to_pj_factor", os.getenv("CLT_TO_PJ_FACTOR", "1.50"))),
        work_hours_month=int(pricing.get("work_hours_month", os.getenv("WORK_HOURS_MONTH", "168"))),
        max_parallel_searches=int(os.getenv("MAX_PARALLEL_SEARCHES", "4")),
        max_parallel_crawls=int(os.getenv("MAX_PARALLEL_CRAWLS", "5")),
        cache_ttl_days=max(1, int(pricing.get("cache_ttl_days", os.getenv("CACHE_TTL_DAYS", "30")))),
        http_timeout_seconds=int(os.getenv("HTTP_TIMEOUT_SECONDS", "10")),
        playwright_timeout_seconds=int(os.getenv("PLAYWRIGHT_TIMEOUT_SECONDS", "20")),
        research_timeout_seconds=int(os.getenv("RESEARCH_TIMEOUT_SECONDS", "120")),
        app_api_key=os.getenv("APP_API_KEY", ""),
    )


def _business_pricing() -> dict[str, Any]:
    """Prefer editable business parameter catalog; fall back to env defaults."""
    try:
        from app.business_settings import get_business_values

        return get_business_values()
    except Exception:
        return {}


def _split_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def load_yaml(path: str | Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return default or {}
    with file_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data if isinstance(data, dict) else default or {}


def provider_config(section: str) -> list[ProviderConfig]:
    providers = load_yaml(CONFIG_DIR / "providers.yaml").get(section, {})
    result = []
    if not isinstance(providers, dict):
        return result
    for name, raw in providers.items():
        raw = raw or {}
        result.append(
            ProviderConfig(
                name=str(name),
                enabled=bool(raw.get("enabled", False)),
                priority=int(raw.get("priority", 100)),
                timeout_seconds=int(raw.get("timeout_seconds", 10)),
                max_results=int(raw.get("max_results", 5)),
                retry_count=int(raw.get("retry_count", 1)),
            )
        )
    return sorted(result, key=lambda item: item.priority)


def append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
