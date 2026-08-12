from __future__ import annotations

from app.compensation.domain.schemas import CompensationResearchRequest, NormalizedProfile
from app.compensation.utils import normalize_text
from app.llm import LocalLLM


async def normalize_profile(request: CompensationResearchRequest, llm: LocalLLM) -> NormalizedProfile:
    prompt = f"""
Retorne JSON estrito com:
role_family, normalized_role, seniority, specialization, skills.
Normalize o perfil de tecnologia abaixo.

Perfil: {request.profile}
Senioridade: {request.seniority}
Skills: {request.skills}
"""
    result = await llm.json_completion(
        "Você normaliza perfis profissionais de tecnologia. Responda apenas JSON válido.",
        prompt,
        timeout=30,
        temperature=0,
        retries=1,
    )
    if result and result.get("normalized_role"):
        return NormalizedProfile(
            role_family=str(result.get("role_family") or "technology"),
            normalized_role=str(result.get("normalized_role")),
            seniority=str(result.get("seniority") or request.seniority),
            specialization=str(result.get("specialization") or ""),
            skills=[str(skill) for skill in result.get("skills", request.skills) if str(skill).strip()],
        )
    return heuristic_normalize_profile(request)


def heuristic_normalize_profile(request: CompensationResearchRequest) -> NormalizedProfile:
    text = normalize_text(" ".join([request.profile, *request.skills]))
    role = request.profile.strip()
    role_family = "technology"
    specialization = ""
    if "arquitet" in text or "architect" in text:
        role = "Cloud Solution Architect" if any(term in text for term in ["cloud", "azure", "aws", "gcp"]) else "Solution Architect"
        role_family = "solution_architecture"
    elif "backend" in text:
        role_family = "software_engineering"
    elif "dados" in text or "data" in text:
        role_family = "data"
    if "azure" in text or "kubernetes" in text or "aks" in text:
        specialization = "cloud_application_architecture"
    return NormalizedProfile(
        role_family=role_family,
        normalized_role=role,
        seniority=request.seniority or "not_specified",
        specialization=specialization,
        skills=request.skills,
    )
