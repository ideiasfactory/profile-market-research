from __future__ import annotations

import re
from typing import Any

from app.compensation.utils import normalize_text


DEFAULT_PREFILL: dict[str, Any] = {
    "profile": "",
    "skills": [],
    "seniority": "senior",
    "allocation_model": "hybrid",
    "target_contract": "PJ",
    "location": {"city": "", "state": "", "country": "BR"},
    "source_job_id": None,
    "source_job_title": None,
}


def map_job_to_compensation_prefill(job: dict[str, Any]) -> dict[str, Any]:
    analysis = job.get("analysis") if isinstance(job.get("analysis"), dict) else {}
    skills = _skills_from_analysis(analysis)
    location = _location_from_job(job)
    profile = str(job.get("title") or "").strip()
    if not profile:
        profile = " ".join(
            part for part in [str(job.get("profile") or "").strip(), str(job.get("seniority") or "").strip()] if part
        )
    return {
        "profile": profile,
        "skills": skills,
        "seniority": map_seniority(str(job.get("seniority") or "")),
        "allocation_model": map_allocation(str(job.get("work_location") or "")),
        "target_contract": map_contract(str(job.get("compensation_type") or "")),
        "location": location,
        "source_job_id": str(job.get("id") or "") or None,
        "source_job_title": str(job.get("title") or "") or None,
        "job_compensation_min": job.get("compensation_min"),
        "job_compensation_max": job.get("compensation_max"),
        "job_compensation_type": job.get("compensation_type"),
    }


def map_seniority(value: str) -> str:
    text = normalize_text(value)
    if any(token in text for token in ("estagio", "estagiario", "intern", "trainee")):
        return "junior"
    if any(token in text for token in ("junior", "jr", "entry")):
        return "junior"
    if any(token in text for token in ("pleno", "mid", "intermediario")):
        return "pleno"
    if any(token in text for token in ("principal", "staff")):
        return "principal"
    if any(token in text for token in ("lead", "tech lead", "lider")):
        return "lead"
    if any(token in text for token in ("especialista", "senior", "sr", "sênior")):
        return "senior"
    return "senior"


def map_allocation(value: str) -> str:
    text = normalize_text(value)
    if "remoto" in text or "remote" in text:
        return "remote"
    if "presencial" in text or "onsite" in text or "on-site" in text:
        return "onsite"
    return "hybrid"


def map_contract(value: str) -> str:
    text = normalize_text(value)
    if text.startswith("clt"):
        return "CLT"
    return "PJ"


def _skills_from_analysis(analysis: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for key in ("must_have", "core_skills", "supporting_skills", "differentials"):
        items = analysis.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            name = ""
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            elif isinstance(item, str):
                name = item.strip()
            if not name:
                continue
            marker = normalize_text(name)
            if marker in seen:
                continue
            seen.add(marker)
            names.append(name)
            if len(names) >= 8:
                return names
    return names


def _location_from_job(job: dict[str, Any]) -> dict[str, str]:
    blobs = [
        str(job.get("description") or ""),
        str(job.get("job_description") or ""),
        str(job.get("ideal_candidate_context") or ""),
        str(job.get("work_location") or ""),
    ]
    text = "\n".join(blobs)
    match = re.search(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç''-]+)\s*/\s*([A-Z]{2})\b",
        text,
    )
    if match:
        return {"city": match.group(1), "state": match.group(2).upper(), "country": "BR"}
    match = re.search(
        r"\b(Campinas|São Paulo|Sao Paulo|Rio de Janeiro|Curitiba|Belo Horizonte|Florian[oó]polis)\s*[-,/]\s*(SP|RJ|PR|MG|SC)\b",
        text,
        flags=re.I,
    )
    if match:
        return {"city": match.group(1), "state": match.group(2).upper(), "country": "BR"}
    return {"city": "", "state": "", "country": "BR"}
