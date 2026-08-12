from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.compensation.domain.schemas import (
    CompensationObservation,
    CompensationResearchRequest,
    ContractType,
    CrawledDocument,
    Location,
    Salary,
    SalaryPeriod,
)
from app.compensation.services.quality import (
    infer_seniority,
    resolve_observation_seniority,
    sanitize_salary_period,
    seniority_compatible,
)
from app.compensation.utils import extract_money_values, normalize_text, now_iso, stable_id
from app.llm import LocalLLM


async def extract_observations(
    document: CrawledDocument,
    request: CompensationResearchRequest,
    normalized_role: str,
    llm: LocalLLM,
) -> list[CompensationObservation]:
    if "R$" not in document.content:
        return []
    prompt = f"""
Extraia somente salários explicitamente evidenciados no conteúdo.
Regras absolutas:
1) se não houver valor salarial explícito, retorne observations=[]
2) NÃO extraia cargos com senioridade incompatível com a senioridade buscada ({request.seniority})
3) se o texto disser Junior/Estágio e a busca for Senior, ignore
4) preserve o período real (hour/month/year); não invente anualização
5) evidence deve conter o trecho com R$ e o cargo/senioridade mencionados
Retorne JSON estrito:
{{
  "is_relevant": true,
  "observations": [
    {{
      "role": "...",
      "seniority": "senior",
      "location": {{"city": "...", "state": "SP", "country": "BR"}},
      "salary_min": 15000,
      "salary_max": 18000,
      "salary_average": 16500,
      "salary_period": "month",
      "contract_type": "CLT",
      "evidence": "trecho com R$ ..."
    }}
  ]
}}

Perfil buscado: {request.profile}
Senioridade buscada: {request.seniority}
Skills: {request.skills}
Fonte: {document.source}
URL: {document.url}
Título: {document.title}
Conteúdo:
{document.content[:10000]}
"""
    result = await llm.json_completion(
        "Você extrai remuneração com evidência. Não calcule e não invente salários. Respeite a senioridade pedida.",
        prompt,
        timeout=45,
        temperature=0,
        retries=1,
    )
    observations = parse_llm_observations(result, document, request, normalized_role) if result else []
    if observations:
        return observations
    return regex_extract_observations(document, request, normalized_role)


def parse_llm_observations(
    result: dict[str, Any],
    document: CrawledDocument,
    request: CompensationResearchRequest,
    normalized_role: str,
) -> list[CompensationObservation]:
    if not result.get("is_relevant"):
        return []
    observations = []
    for item in result.get("observations", []):
        evidence = str(item.get("evidence") or "")
        if "R$" not in evidence:
            continue
        role = str(item.get("role") or request.profile)
        detected_seniority = infer_seniority(
            role, evidence, document.url, document.title, str(item.get("seniority") or "")
        )
        if detected_seniority and not seniority_compatible(detected_seniority, request.seniority):
            continue
        salary = Salary(
            min=_float_or_none(item.get("salary_min")),
            max=_float_or_none(item.get("salary_max")),
            average=_float_or_none(item.get("salary_average")),
            period=_period(item.get("salary_period"), evidence),
        )
        salary = sanitize_salary_period(salary, evidence)
        if salary is None:
            continue
        location_raw = item.get("location") if isinstance(item.get("location"), dict) else {}
        try:
            observation = CompensationObservation(
                id=stable_id(document.url, evidence, salary.model_dump()),
                role=role,
                normalized_role=normalized_role,
                seniority=detected_seniority or str(item.get("seniority") or request.seniority),
                skills=request.skills,
                location=Location(
                    city=str(location_raw.get("city") or request.location.city),
                    state=str(location_raw.get("state") or request.location.state),
                    country=str(location_raw.get("country") or request.location.country or "BR"),
                ),
                allocation_model=request.allocation_model,
                employment_type=_contract(item.get("contract_type")),
                salary=salary,
                source=document.source,
                source_url=document.url,
                evidence=evidence[:500],
                evidence_type="search_snippet" if document.crawl_method == "search_snippet" else "page_content",
                retrieved_at=document.retrieved_at,
                crawl_method=document.crawl_method,
                confidence=0.7 if document.crawl_method == "search_snippet" else 0.85,
            )
            observation = observation.model_copy(
                update={"seniority": resolve_observation_seniority(observation, request.seniority)}
            )
            if not seniority_compatible(observation.seniority, request.seniority):
                continue
            observations.append(observation)
        except ValidationError:
            continue
    return observations


def regex_extract_observations(
    document: CrawledDocument,
    request: CompensationResearchRequest,
    normalized_role: str,
) -> list[CompensationObservation]:
    detected = infer_seniority(document.title, document.content, document.url)
    if detected and not seniority_compatible(detected, request.seniority):
        return []

    evidence = evidence_window(document.content)
    if "R$" not in evidence:
        return []
    if not has_salary_context(evidence):
        return []
    evidence_seniority = infer_seniority(evidence, document.title, document.url)
    if evidence_seniority and not seniority_compatible(evidence_seniority, request.seniority):
        return []

    values = extract_money_values(evidence)
    values = [value for value in values if value >= 40]
    if not values:
        return []
    period = infer_period(evidence, values)
    contract = infer_contract(evidence)
    salary = Salary(
        min=min(values),
        max=max(values) if len(values) > 1 else None,
        average=sum(values) / len(values),
        period=period,
    )
    salary = sanitize_salary_period(salary, evidence)
    if salary is None:
        return []
    observation = CompensationObservation(
        id=stable_id(document.url, evidence, salary.model_dump()),
        role=request.profile,
        normalized_role=normalized_role,
        seniority=evidence_seniority or request.seniority,
        skills=request.skills,
        location=request.location,
        allocation_model=request.allocation_model,
        employment_type=contract,
        salary=salary,
        source=document.source,
        source_url=document.url,
        evidence=evidence[:500],
        evidence_type="search_snippet" if document.crawl_method == "search_snippet" else "page_content",
        retrieved_at=document.retrieved_at or now_iso(),
        crawl_method=document.crawl_method,
        confidence=0.55 if document.crawl_method == "search_snippet" else 0.75,
    )
    observation = observation.model_copy(
        update={"seniority": resolve_observation_seniority(observation, request.seniority)}
    )
    if not seniority_compatible(observation.seniority, request.seniority):
        return []
    return [observation]


def evidence_window(text: str) -> str:
    match = re.search(
        r".{0,120}(?:sal[aá]rio|remunera[cç][aã]o|faixa salarial).{0,80}R\$\s*[0-9][^\n]{0,180}"
        r"|.{0,80}R\$\s*[0-9][^\n]{0,120}(?:\/m[eê]s|\/h|por m[eê]s|por hora|ao ano|anual)",
        text or "",
        flags=re.I | re.S,
    )
    return " ".join(match.group(0).split()) if match else ""


def has_salary_context(text: str) -> bool:
    normalized = normalize_text(text)
    keywords = ("salario", "remuneracao", "faixa salarial", "/mes", "/h", "por mes", "por hora", "anual", "ao ano")
    return any(keyword in normalized for keyword in keywords)


def infer_period(text: str, values: list[float]) -> SalaryPeriod:
    normalized = normalize_text(text)
    if "/h" in normalized or "por hora" in normalized:
        return SalaryPeriod.hour
    if "ao ano" in normalized or "anual" in normalized or "/ano" in normalized:
        return SalaryPeriod.year
    if "mil" in normalized or "/mes" in normalized or "mensal" in normalized or any(value >= 3000 for value in values):
        return SalaryPeriod.month
    if values and all(40 <= value < 1000 for value in values):
        return SalaryPeriod.hour
    return SalaryPeriod.month


def infer_contract(text: str) -> ContractType:
    normalized = normalize_text(text)
    if "pj" in normalized or "pessoa juridica" in normalized:
        return ContractType.PJ
    return ContractType.CLT


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _period(value: Any, evidence: str = "") -> SalaryPeriod:
    try:
        return SalaryPeriod(str(value))
    except ValueError:
        return infer_period(evidence, [])


def _contract(value: Any) -> ContractType:
    try:
        return ContractType(str(value).upper())
    except ValueError:
        return ContractType.CLT
