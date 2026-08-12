from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.storage import DATA_DIR, JsonStore, new_id


VALUE_TYPES = ("number", "percent", "text", "boolean")

# Seed examples only — the catalog is open; operators can add any business keys.
DEFAULT_PARAMETERS: list[dict[str, Any]] = [
    {
        "id": "param_clt_to_pj_factor",
        "key": "clt_to_pj_factor",
        "label": "Fator CLT → PJ",
        "value": 1.5,
        "value_type": "number",
        "category": "compensation",
        "description": "Conversão de salário CLT mensal para equivalente PJ mensal na research de mercado.",
        "inject_in_prompts": True,
    },
    {
        "id": "param_work_hours_month",
        "key": "work_hours_month",
        "label": "Horas por mês",
        "value": 168,
        "value_type": "number",
        "category": "compensation",
        "description": "Base para converter remuneração mensal ↔ horária.",
        "inject_in_prompts": True,
    },
    {
        "id": "param_iss_pct",
        "key": "iss_pct",
        "label": "ISS (%)",
        "value": 5.0,
        "value_type": "percent",
        "category": "pricing",
        "description": "Exemplo de imposto municipal sobre serviços. Ajuste ou remova conforme o negócio.",
        "inject_in_prompts": True,
    },
    {
        "id": "param_pis_cofins_pct",
        "key": "pis_cofins_pct",
        "label": "PIS + COFINS (%)",
        "value": 3.65,
        "value_type": "percent",
        "category": "pricing",
        "description": "Exemplo de carga federal sobre receita. Pode ser substituído por outro modelo tributário.",
        "inject_in_prompts": True,
    },
    {
        "id": "param_overhead_pct",
        "key": "overhead_pct",
        "label": "Overhead (%)",
        "value": 10.0,
        "value_type": "percent",
        "category": "pricing",
        "description": "Exemplo de custos indiretos (estrutura, comercial, ferramentas).",
        "inject_in_prompts": True,
    },
    {
        "id": "param_target_margin_pct",
        "key": "target_margin_pct",
        "label": "Margem alvo (%)",
        "value": 25.0,
        "value_type": "percent",
        "category": "pricing",
        "description": "Exemplo de margem desejada sobre o preço de venda ao cliente.",
        "inject_in_prompts": True,
    },
]

DEFAULT_BUSINESS_SETTINGS: dict[str, Any] = {
    "parameters": deepcopy(DEFAULT_PARAMETERS),
    "updated_at": None,
}


business_settings_store = JsonStore(DATA_DIR / "business_settings.json", deepcopy(DEFAULT_BUSINESS_SETTINGS))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug_key(raw: str) -> str:
    text = (raw or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:64] or f"param_{new_id()[:8]}"


def _coerce_value(value: Any, value_type: str) -> Any:
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "sim", "on"}
    if value_type == "text":
        return str(value if value is not None else "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if value_type == "number" and number == int(number):
        return int(number)
    return round(number, 6)


def _normalize_parameter(raw: dict[str, Any] | None, *, fallback_id: str | None = None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    key = _slug_key(str(raw.get("key") or raw.get("name") or ""))
    if not key:
        return None
    value_type = str(raw.get("value_type") or "text").strip().lower()
    if value_type not in VALUE_TYPES:
        value_type = "text"
    label = str(raw.get("label") or key).strip() or key
    category = _slug_key(str(raw.get("category") or "geral")) or "geral"
    description = str(raw.get("description") or "").strip()
    inject = raw.get("inject_in_prompts", True)
    if isinstance(inject, str):
        inject = inject.strip().lower() in {"1", "true", "yes", "sim", "on"}
    else:
        inject = bool(inject)
    return {
        "id": str(raw.get("id") or fallback_id or f"param_{new_id()}"),
        "key": key,
        "label": label,
        "value": _coerce_value(raw.get("value"), value_type),
        "value_type": value_type,
        "category": category,
        "description": description,
        "inject_in_prompts": inject,
    }


def _migrate_legacy_pricing(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert first-version {pricing: {...}} payload into parameter rows."""
    pricing = raw.get("pricing")
    if not isinstance(pricing, dict):
        return []
    defaults_by_key = {item["key"]: item for item in DEFAULT_PARAMETERS}
    migrated: list[dict[str, Any]] = []
    for key, value in pricing.items():
        base = deepcopy(defaults_by_key.get(key)) or {
            "id": f"param_{key}",
            "key": key,
            "label": key,
            "value_type": "percent" if str(key).endswith("_pct") else "number",
            "category": "pricing",
            "description": "",
            "inject_in_prompts": True,
        }
        base["value"] = value
        normalized = _normalize_parameter(base)
        if normalized:
            migrated.append(normalized)
    return migrated


def normalize_business_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    parameters_raw = incoming.get("parameters")
    if not isinstance(parameters_raw, list):
        parameters_raw = _migrate_legacy_pricing(incoming)
    if not parameters_raw:
        parameters_raw = deepcopy(DEFAULT_PARAMETERS)

    parameters: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in parameters_raw:
        normalized = _normalize_parameter(item if isinstance(item, dict) else None)
        if not normalized or normalized["key"] in seen_keys:
            continue
        seen_keys.add(normalized["key"])
        parameters.append(normalized)

    parameters.sort(key=lambda item: (item["category"], item["label"].lower(), item["key"]))
    return {
        "parameters": parameters,
        "values": {item["key"]: item["value"] for item in parameters},
        "updated_at": incoming.get("updated_at"),
    }


def get_business_settings() -> dict[str, Any]:
    raw = business_settings_store.read()
    settings = normalize_business_settings(raw)
    # Persist migration from legacy {pricing: ...} shape once.
    if isinstance(raw, dict) and "parameters" not in raw and "pricing" in raw:
        business_settings_store.write(
            {
                "parameters": settings["parameters"],
                "updated_at": settings.get("updated_at") or _now_iso(),
            }
        )
        settings["updated_at"] = settings.get("updated_at") or _now_iso()
    return settings


def get_business_values() -> dict[str, Any]:
    return get_business_settings()["values"]


def get_business_parameter(key: str, default: Any = None) -> Any:
    return get_business_values().get(key, default)


def save_business_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = normalize_business_settings(payload)
    if not settings["parameters"]:
        raise ValueError("Informe ao menos um parâmetro de negócio.")
    settings["updated_at"] = _now_iso()
    business_settings_store.write(
        {
            "parameters": settings["parameters"],
            "updated_at": settings["updated_at"],
        }
    )
    return settings


def upsert_business_parameter(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_business_settings()
    incoming = _normalize_parameter(payload)
    if not incoming:
        raise ValueError("Parâmetro inválido: informe uma chave.")
    parameters = settings["parameters"]
    replaced = False
    for index, existing in enumerate(parameters):
        same_id = payload.get("id") and existing["id"] == payload.get("id")
        same_key = existing["key"] == incoming["key"]
        if same_id or same_key:
            if not same_id and any(item["key"] == incoming["key"] and item["id"] != existing["id"] for item in parameters):
                raise ValueError(f"Já existe um parâmetro com a chave '{incoming['key']}'.")
            incoming["id"] = existing["id"]
            parameters[index] = incoming
            replaced = True
            break
    if not replaced:
        if any(item["key"] == incoming["key"] for item in parameters):
            raise ValueError(f"Já existe um parâmetro com a chave '{incoming['key']}'.")
        parameters.append(incoming)
    return save_business_settings({"parameters": parameters})


def delete_business_parameter(item_id: str) -> dict[str, Any]:
    settings = get_business_settings()
    remaining = [
        item
        for item in settings["parameters"]
        if item["id"] != item_id and item["key"] != item_id
    ]
    if len(remaining) == len(settings["parameters"]):
        raise ValueError("Parâmetro não encontrado.")
    return save_business_settings({"parameters": remaining})


def format_business_context(parameters: list[dict[str, Any]] | None = None) -> str:
    """Texto pronto para embutir em prompts via {business_context}."""
    items = parameters if parameters is not None else get_business_settings()["parameters"]
    lines: list[str] = []
    for item in items:
        if not item.get("inject_in_prompts", True):
            continue
        value = item["value"]
        if item["value_type"] == "percent":
            rendered = f"{value}%"
        elif item["value_type"] == "boolean":
            rendered = "sim" if value else "não"
        else:
            rendered = str(value)
        label = item["label"]
        desc = f" — {item['description']}" if item.get("description") else ""
        lines.append(f"- {label} (`{item['key']}`): {rendered}{desc}")
    if not lines:
        return "(nenhum parâmetro de negócio habilitado para prompts)"
    return "Parâmetros de negócio:\n" + "\n".join(lines)


def prompt_placeholders() -> dict[str, str]:
    """Placeholders para `load_prompt`: cada chave + bloco `business_context`."""
    settings = get_business_settings()
    placeholders: dict[str, str] = {
        "business_context": format_business_context(settings["parameters"]),
    }
    for item in settings["parameters"]:
        if not item.get("inject_in_prompts", True):
            continue
        value = item["value"]
        if item["value_type"] == "boolean":
            placeholders[item["key"]] = "true" if value else "false"
        else:
            placeholders[item["key"]] = str(value)
    return placeholders
