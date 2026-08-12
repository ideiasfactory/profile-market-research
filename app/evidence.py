from __future__ import annotations

from typing import Any

from app.scoring_config import EVIDENCE_STATUSES


SOFT_CATEGORY_MARKERS = {"Soft skill", "soft_skills", "SOFT"}


def normalize_evidence_list(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, str) and raw.strip():
        return [{"text": raw.strip()[:400], "source": "resume"}]
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append({"text": item.strip()[:400], "source": "resume"})
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("evidence") or item.get("snippet") or "").strip()
        if not text:
            continue
        source = str(item.get("source") or "resume").strip()[:40] or "resume"
        out.append({"text": text[:400], "source": source})
    return out[:5]


def normalize_evidence_status(raw: Any, *, score: int | None, is_soft: bool) -> str:
    status = str(raw or "").strip().lower()
    aliases = {
        "explicit": "explicit",
        "explicito": "explicit",
        "explícito": "explicit",
        "inferred": "inferred",
        "inferido": "inferred",
        "not_found": "not_found",
        "nao_encontrado": "not_found",
        "não_encontrado": "not_found",
        "absent": "not_found",
        "negative": "negative",
        "negativo": "negative",
        "needs_validation": "needs_validation",
        "validar": "needs_validation",
        "pending": "needs_validation",
    }
    mapped = aliases.get(status, status if status in EVIDENCE_STATUSES else "")
    if mapped:
        return mapped
    if score is None and is_soft:
        return "needs_validation"
    if score is None or score <= 0:
        return "not_found"
    return "explicit"


def evidence_to_legacy_text(evidence: list[dict[str, str]], status: str) -> str:
    if evidence:
        return evidence[0]["text"][:300]
    defaults = {
        "not_found": "Sem evidência textual no currículo.",
        "needs_validation": "Sem evidência textual; validar em entrevista.",
        "negative": "Evidência negativa ou contraditória.",
        "inferred": "Inferência fraca; validar com evidência direta.",
        "explicit": "Evidência identificada no currículo.",
    }
    return defaults.get(status, "Sem avaliação.")


def is_soft_skill(skill: dict[str, Any]) -> bool:
    tier = str(skill.get("tier") or "").upper()
    category = str(skill.get("category") or "")
    return tier == "SOFT" or category in SOFT_CATEGORY_MARKERS
