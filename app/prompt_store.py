from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.storage import DATA_DIR, JsonStore


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Catalog metadata for known prompt files (title + purpose).
PROMPT_CATALOG: list[dict[str, str]] = [
    {
        "id": "analyse_job.system.txt",
        "title": "Análise de vaga — system",
        "description": "Instruções de sistema para extrair requisitos, tiers e skill groups a partir da job description.",
        "group": "Análise de vaga",
    },
    {
        "id": "analyse_job.user.txt",
        "title": "Análise de vaga — user",
        "description": "Template do usuário com schema JSON esperado e o texto da vaga ({title}, {job_description}, etc.).",
        "group": "Análise de vaga",
    },
    {
        "id": "extract_candidate.system.txt",
        "title": "Extração de currículo — system",
        "description": "Instruções para extrair nome, cidade e cargo reportado do texto do currículo.",
        "group": "Currículo",
    },
    {
        "id": "extract_candidate.user.txt",
        "title": "Extração de currículo — user",
        "description": "Prompt do usuário com o conteúdo do currículo ({resume_text}).",
        "group": "Currículo",
    },
    {
        "id": "score_skills.system.txt",
        "title": "Score de skills — system",
        "description": "Avalia evidências de skills do candidato (status, score, evidências) com anti-alucinação.",
        "group": "Scoring",
    },
    {
        "id": "score_skills.user.txt",
        "title": "Score de skills — user",
        "description": "Lista de skills da vaga + currículo para pontuação individual.",
        "group": "Scoring",
    },
    {
        "id": "openai/score_weights.system.txt",
        "title": "Pesos OpenAI (v3) — system",
        "description": "Recalibra pesos/tiers de skills da vaga via OpenAI no scoring model v3 (sem inventar skills).",
        "group": "Scoring OpenAI",
    },
    {
        "id": "openai/score_weights.user.txt",
        "title": "Pesos OpenAI (v3) — user",
        "description": "JD + current_skills JSON para recalibração discriminativa de pesos (modelo v3).",
        "group": "Scoring OpenAI",
    },
    {
        "id": "openai/analyse_job.system.txt",
        "title": "Análise de vaga OpenAI — system",
        "description": "Extrai requisitos/tiers/pesos discriminativos da JD via OpenAI (comparativo com prompts locais).",
        "group": "Análise OpenAI",
    },
    {
        "id": "openai/analyse_job.user.txt",
        "title": "Análise de vaga OpenAI — user",
        "description": "Schema JSON e regras de pesos amplos (1–10 discriminativos) para análise de vaga com OpenAI.",
        "group": "Análise OpenAI",
    },
    {
        "id": "score_fit.system.txt",
        "title": "Role / Context Fit — system",
        "description": "Avalia aderência de role fit e context fit além das skills pontuadas.",
        "group": "Scoring",
    },
    {
        "id": "score_fit.user.txt",
        "title": "Role / Context Fit — user",
        "description": "Contexto da vaga, candidato e skills já pontuadas para o fit composto.",
        "group": "Scoring",
    },
    {
        "id": "score_narrative.system.txt",
        "title": "Narrativa / veredito — system",
        "description": "Gera resumo executivo, pontos fortes/lacunas e veredito textual do score.",
        "group": "Scoring",
    },
    {
        "id": "score_narrative.user.txt",
        "title": "Narrativa / veredito — user",
        "description": "Entrada com score final, strengths/gaps e trechos do currículo para a narrativa.",
        "group": "Scoring",
    },
    {
        "id": "score_candidate.system.txt",
        "title": "Score legado (v1) — system",
        "description": "Prompt legado de scoring flat (compatibilidade). Preferir o fluxo v2 (skills/fit/narrative).",
        "group": "Legado",
    },
    {
        "id": "score_candidate.user.txt",
        "title": "Score legado (v1) — user",
        "description": "Template legado do usuário para scoring flat candidato-vaga.",
        "group": "Legado",
    },
]


prompt_store = JsonStore(DATA_DIR / "prompt_store.json", {"prompts": {}, "updated_at": None})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_version_id() -> str:
    return f"v_{uuid4().hex[:10]}"


def _read_disk_prompt(prompt_id: str) -> str:
    path = (PROMPTS_DIR / prompt_id).resolve()
    if not path.is_relative_to(PROMPTS_DIR.resolve()):
        raise FileNotFoundError(f"Prompt inválido: {prompt_id}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8").strip()


def _catalog_meta(prompt_id: str) -> dict[str, str]:
    for item in PROMPT_CATALOG:
        if item["id"] == prompt_id:
            return item
    return {
        "id": prompt_id,
        "title": prompt_id,
        "description": "Prompt customizado / arquivo em prompts/.",
        "group": "Outros",
    }


def _ensure_prompt_record(raw_store: dict[str, Any], prompt_id: str) -> dict[str, Any]:
    prompts = raw_store.setdefault("prompts", {})
    if not isinstance(prompts, dict):
        prompts = {}
        raw_store["prompts"] = prompts
    record = prompts.get(prompt_id)
    if isinstance(record, dict) and record.get("versions"):
        return record

    meta = _catalog_meta(prompt_id)
    content = _read_disk_prompt(prompt_id)
    version_id = _new_version_id()
    record = {
        "id": prompt_id,
        "title": meta["title"],
        "description": meta["description"],
        "group": meta["group"],
        "active_version_id": version_id,
        "versions": [
            {
                "id": version_id,
                "label": "v1 (baseline arquivo)",
                "created_at": _now_iso(),
                "source": "disk",
                "content": content,
            }
        ],
    }
    prompts[prompt_id] = record
    return record


def _sync_catalog(raw_store: dict[str, Any]) -> bool:
    """Ensure all catalog + disk prompts exist in the store. Returns True if mutated."""
    changed = False
    known_ids = {item["id"] for item in PROMPT_CATALOG}
    for path in sorted(PROMPTS_DIR.rglob("*.txt")):
        known_ids.add(path.relative_to(PROMPTS_DIR).as_posix())
    for prompt_id in sorted(known_ids):
        if prompt_id not in (raw_store.get("prompts") or {}):
            _ensure_prompt_record(raw_store, prompt_id)
            changed = True
        else:
            record = raw_store["prompts"][prompt_id]
            meta = _catalog_meta(prompt_id)
            # Keep catalog title/description if operator never customized them.
            if not record.get("title"):
                record["title"] = meta["title"]
                changed = True
            if not record.get("description"):
                record["description"] = meta["description"]
                changed = True
            if not record.get("group"):
                record["group"] = meta["group"]
                changed = True
    return changed


def _active_version(record: dict[str, Any]) -> dict[str, Any]:
    versions = record.get("versions") or []
    active_id = record.get("active_version_id")
    for version in versions:
        if version.get("id") == active_id:
            return version
    if versions:
        return versions[-1]
    raise ValueError(f"Prompt sem versões: {record.get('id')}")


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    active = _active_version(record)
    versions = sorted(record.get("versions") or [], key=lambda item: item.get("created_at") or "", reverse=True)
    return {
        "id": record["id"],
        "title": record.get("title") or record["id"],
        "description": record.get("description") or "",
        "group": record.get("group") or "Outros",
        "active_version_id": active["id"],
        "active_label": active.get("label") or active["id"],
        "content": active.get("content") or "",
        "version_count": len(versions),
        "versions": [
            {
                "id": item["id"],
                "label": item.get("label") or item["id"],
                "created_at": item.get("created_at"),
                "source": item.get("source") or "edit",
                "is_active": item["id"] == active["id"],
            }
            for item in versions
        ],
    }


def list_managed_prompts() -> list[dict[str, Any]]:
    raw = prompt_store.read()
    if not isinstance(raw, dict):
        raw = {"prompts": {}}
    if _sync_catalog(raw):
        raw["updated_at"] = _now_iso()
        prompt_store.write(raw)
    items = [_public_record(record) for record in (raw.get("prompts") or {}).values()]
    items.sort(key=lambda item: (item.get("group") or "", item.get("title") or ""))
    return items


def get_managed_prompt(prompt_id: str, *, version_id: str | None = None) -> dict[str, Any]:
    raw = prompt_store.read()
    if not isinstance(raw, dict):
        raw = {"prompts": {}}
    if _sync_catalog(raw):
        raw["updated_at"] = _now_iso()
        prompt_store.write(raw)
    record = _ensure_prompt_record(raw, prompt_id)
    if prompt_id not in (raw.get("prompts") or {}):
        prompt_store.write(raw)
    public = _public_record(record)
    if version_id:
        for version in record.get("versions") or []:
            if version.get("id") == version_id:
                public = {
                    **public,
                    "viewing_version_id": version_id,
                    "content": version.get("content") or "",
                    "active_label": version.get("label") or version_id,
                }
                break
        else:
            raise ValueError(f"Versão não encontrada: {version_id}")
    return public


def get_active_prompt_content(prompt_id: str) -> str | None:
    """Return active override content if the store has this prompt; else None (use disk)."""
    raw = prompt_store.read()
    if not isinstance(raw, dict):
        return None
    prompts = raw.get("prompts")
    if not isinstance(prompts, dict) or prompt_id not in prompts:
        return None
    record = prompts[prompt_id]
    if not isinstance(record, dict) or not record.get("versions"):
        return None
    return str(_active_version(record).get("content") or "")


def save_prompt_edit(
    prompt_id: str,
    *,
    content: str,
    title: str | None = None,
    description: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    raw = prompt_store.read()
    if not isinstance(raw, dict):
        raw = {"prompts": {}}
    _sync_catalog(raw)
    record = _ensure_prompt_record(raw, prompt_id)
    new_content = (content or "").strip()
    if not new_content:
        raise ValueError("O conteúdo do prompt não pode ficar vazio.")

    active = _active_version(record)
    title_changed = title is not None and title.strip() and title.strip() != record.get("title")
    description_changed = (
        description is not None and description.strip() != (record.get("description") or "")
    )
    content_changed = new_content != (active.get("content") or "").strip()

    if title is not None and title.strip():
        record["title"] = title.strip()
    if description is not None:
        record["description"] = description.strip()

    if content_changed:
        version_number = len(record.get("versions") or []) + 1
        version_id = _new_version_id()
        label_note = note.strip() or "edição manual"
        record.setdefault("versions", []).append(
            {
                "id": version_id,
                "label": f"v{version_number} ({label_note})",
                "created_at": _now_iso(),
                "source": "edit",
                "content": new_content,
            }
        )
        record["active_version_id"] = version_id
    elif not (title_changed or description_changed):
        raise ValueError("Nenhuma alteração detectada.")

    raw["updated_at"] = _now_iso()
    prompt_store.write(raw)
    _invalidate_prompt_cache()
    return get_managed_prompt(prompt_id)


def revert_prompt_version(prompt_id: str, version_id: str) -> dict[str, Any]:
    raw = prompt_store.read()
    if not isinstance(raw, dict):
        raw = {"prompts": {}}
    _sync_catalog(raw)
    record = _ensure_prompt_record(raw, prompt_id)
    target = None
    for version in record.get("versions") or []:
        if version.get("id") == version_id:
            target = version
            break
    if target is None:
        raise ValueError(f"Versão não encontrada: {version_id}")

    if record.get("active_version_id") == version_id:
        return get_managed_prompt(prompt_id)

    # Create a new version that copies the selected content (audit-friendly revert).
    version_number = len(record.get("versions") or []) + 1
    new_id = _new_version_id()
    record.setdefault("versions", []).append(
        {
            "id": new_id,
            "label": f"v{version_number} (revert de {target.get('label') or version_id})",
            "created_at": _now_iso(),
            "source": "revert",
            "reverted_from": version_id,
            "content": target.get("content") or "",
        }
    )
    record["active_version_id"] = new_id
    raw["updated_at"] = _now_iso()
    prompt_store.write(raw)
    _invalidate_prompt_cache()
    return get_managed_prompt(prompt_id)


def get_prompt_version_content(prompt_id: str, version_id: str) -> str:
    record = get_managed_prompt(prompt_id)
    # Need full content from store
    raw = prompt_store.read()
    versions = ((raw.get("prompts") or {}).get(prompt_id) or {}).get("versions") or []
    for version in versions:
        if version.get("id") == version_id:
            return str(version.get("content") or "")
    raise ValueError(f"Versão não encontrada: {version_id}")


def _invalidate_prompt_cache() -> None:
    try:
        from app.prompts import clear_prompt_cache

        clear_prompt_cache()
    except Exception:
        pass


def grouped_managed_prompts() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in list_managed_prompts():
        grouped.setdefault(item.get("group") or "Outros", []).append(item)
    return grouped
