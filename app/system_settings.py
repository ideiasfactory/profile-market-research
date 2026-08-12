from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.storage import DATA_DIR, JsonStore


# Fixed system catalog (not free-form). Secrets never go into LLM prompts.
SYSTEM_PARAMETER_DEFS: list[dict[str, Any]] = [
    {
        "key": "TAVILY_API_KEY",
        "label": "Tavily API Key",
        "category": "apis",
        "value_type": "secret",
        "description": "Chave Bearer/API do Tavily Search (usada em research de compensation).",
        "env_keys": ["TAVILY_API_KEY"],
        "default": "",
    },
    {
        "key": "TAVILY_BASE_URL",
        "label": "Tavily Base URL",
        "category": "apis",
        "value_type": "url",
        "description": "Endpoint base da API Tavily.",
        "env_keys": ["TAVILY_BASE_URL"],
        "default": "https://api.tavily.com",
    },
    {
        "key": "FIRECRAWL_API_KEY",
        "label": "Firecrawl API Key",
        "category": "apis",
        "value_type": "secret",
        "description": "Chave Bearer do Firecrawl (search/crawl).",
        "env_keys": ["FIRECRAWL_API_KEY"],
        "default": "",
    },
    {
        "key": "FIRECRAWL_BASE_URL",
        "label": "Firecrawl Base URL",
        "category": "apis",
        "value_type": "url",
        "description": "Endpoint base da API Firecrawl.",
        "env_keys": ["FIRECRAWL_BASE_URL"],
        "default": "https://api.firecrawl.dev",
    },
    {
        "key": "OLLAMA_BASE_URL",
        "label": "Ollama / LLM Base URL",
        "category": "llm",
        "value_type": "url",
        "description": "URL do Ollama (também usada como LOCAL_LLM_URL).",
        "env_keys": ["OLLAMA_BASE_URL", "LOCAL_LLM_URL"],
        "default": "http://gpu-server-01:11434",
    },
    {
        "key": "OLLAMA_MODEL",
        "label": "Ollama / LLM Model",
        "category": "llm",
        "value_type": "text",
        "description": "Modelo padrão do Ollama (também LOCAL_LLM_MODEL).",
        "env_keys": ["OLLAMA_MODEL", "LOCAL_LLM_MODEL"],
        "default": "qwen2.5:14b",
    },
    {
        "key": "PROFESSIONAL_PROFILE_API_KEY",
        "label": "API Key do PPA (/api/gpt)",
        "category": "security",
        "value_type": "secret",
        "description": "Quando definida, /api/gpt/* exige Bearer ou X-API-Key.",
        "env_keys": ["PROFESSIONAL_PROFILE_API_KEY"],
        "default": "",
    },
]


system_settings_store = JsonStore(DATA_DIR / "system_settings.json", {"values": {}, "updated_at": None})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_lookup(env_keys: list[str], default: str = "") -> str:
    for key in env_keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def mask_secret(value: str | None, visible: int = 4) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= visible:
        return "•" * len(text)
    return f"{'•' * max(8, len(text) - visible)}{text[-visible:]}"


def get_system_value(key: str, default: str | None = None) -> str:
    """Resolve system value: persisted override → env → catalog default."""
    stored = system_settings_store.read()
    values = stored.get("values") if isinstance(stored, dict) else {}
    if isinstance(values, dict) and key in values and str(values.get(key) or "").strip() != "":
        return str(values[key]).strip()
    for item in SYSTEM_PARAMETER_DEFS:
        if item["key"] != key:
            continue
        return _env_lookup(item["env_keys"], item.get("default") if default is None else (default or ""))
    if default is not None:
        return default
    return os.getenv(key, "") or ""


def get_system_settings(*, reveal_secrets: bool = False) -> dict[str, Any]:
    stored = system_settings_store.read()
    stored_values = stored.get("values") if isinstance(stored, dict) else {}
    if not isinstance(stored_values, dict):
        stored_values = {}

    parameters: list[dict[str, Any]] = []
    values: dict[str, str] = {}
    for item in SYSTEM_PARAMETER_DEFS:
        key = item["key"]
        raw = ""
        if key in stored_values and str(stored_values.get(key) or "").strip() != "":
            raw = str(stored_values[key]).strip()
            source = "store"
        else:
            raw = _env_lookup(item["env_keys"], str(item.get("default") or ""))
            source = "env" if raw and raw != item.get("default") else ("default" if raw == item.get("default") else "missing")
            if raw and _env_lookup(item["env_keys"], "") == raw:
                source = "env"
            elif raw == item.get("default"):
                source = "default"
            elif not raw:
                source = "missing"

        values[key] = raw
        display = raw if (reveal_secrets or item["value_type"] != "secret") else mask_secret(raw)
        parameters.append(
            {
                **deepcopy(item),
                "value": display,
                "has_value": bool(raw),
                "source": source,
            }
        )

    grouped: dict[str, list] = {}
    for param in parameters:
        grouped.setdefault(param["category"], []).append(param)

    return {
        "parameters": parameters,
        "grouped": grouped,
        "values": values,
        "updated_at": stored.get("updated_at") if isinstance(stored, dict) else None,
    }


def save_system_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Persist overrides. Empty secret fields keep the previous value."""
    if not isinstance(updates, dict):
        raise ValueError("Payload inválido")
    stored = system_settings_store.read()
    values = dict(stored.get("values") or {}) if isinstance(stored, dict) else {}
    known = {item["key"]: item for item in SYSTEM_PARAMETER_DEFS}

    for key, raw_value in updates.items():
        if key not in known:
            continue
        meta = known[key]
        text = "" if raw_value is None else str(raw_value).strip()
        if meta["value_type"] == "secret" and text == "":
            continue  # keep existing
        if meta["value_type"] == "secret" and set(text) <= {"•", "*"}:
            continue  # ignore masked placeholder submissions
        values[key] = text
        for env_key in meta["env_keys"]:
            if text:
                os.environ[env_key] = text
            elif env_key in os.environ and meta["value_type"] != "secret":
                # Non-secret cleared: remove override from process env if we own it
                pass

    # Apply non-empty values to process env for immediate effect
    for key, meta in known.items():
        value = values.get(key) or _env_lookup(meta["env_keys"], str(meta.get("default") or ""))
        if value:
            for env_key in meta["env_keys"]:
                os.environ[env_key] = value

    payload = {"values": values, "updated_at": _now_iso()}
    system_settings_store.write(payload)
    return get_system_settings(reveal_secrets=False)


def apply_system_settings_to_environ() -> None:
    """Call at startup so adapters see store overrides after load_app_env()."""
    settings = get_system_settings(reveal_secrets=True)
    for item in SYSTEM_PARAMETER_DEFS:
        value = settings["values"].get(item["key"]) or ""
        if not value:
            continue
        for env_key in item["env_keys"]:
            os.environ[env_key] = value
