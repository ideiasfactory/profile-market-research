from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.evidence import (
    evidence_to_legacy_text,
    is_soft_skill,
    normalize_evidence_list,
    normalize_evidence_status,
)
from app.job_understanding import (
    flatten_skills_v2,
    normalize_job_analysis,
    skill_group_index,
)
from app.llm import LLMClient
from app.llm_usage import aggregate_usage, aggregate_usage_from_audits, usage_from_audit_payload
from app.prompts import load_prompt
from app.scoring_config import (
    JOB_ANALYSIS_VERSION,
    PROMPT_VERSIONS,
    active_scoring_model,
)
from app.scoring_v2 import (
    build_v2_score_result,
    decide_verdict,
    verdict_label_v1_from_score,
)


# Cada item: nome de exibição + padrões de busca (texto já será normalizado).
# Padrões curtos usam fronteira de palavra para evitar falsos positivos (ex.: git em "digital").
TECH_SKILLS: list[dict[str, Any]] = [
    {"name": "Python", "patterns": ["python"]},
    {"name": "Java", "patterns": ["java"]},
    {"name": "JavaScript", "patterns": ["javascript"]},
    {"name": "TypeScript", "patterns": ["typescript"]},
    {"name": "React", "patterns": ["react"]},
    {"name": "Node.js", "patterns": ["nodejs", "node.js", "node"]},
    {"name": "FastAPI", "patterns": ["fastapi"]},
    {"name": "Django", "patterns": ["django"]},
    {"name": "Spring", "patterns": ["spring"]},
    {"name": "SQL", "patterns": ["sql"]},
    {"name": "PostgreSQL", "patterns": ["postgresql", "postgres"]},
    {"name": "MySQL", "patterns": ["mysql"]},
    {"name": "MongoDB", "patterns": ["mongodb"]},
    {"name": "Redis", "patterns": ["redis"]},
    {"name": "AWS", "patterns": ["aws", "amazon web services"]},
    {"name": "Azure", "patterns": ["azure"]},
    {"name": "Azure Integration Services", "patterns": ["azure integration services"]},
    {"name": "GCP", "patterns": ["gcp", "google cloud"]},
    {"name": "Docker", "patterns": ["docker"]},
    {"name": "Kubernetes", "patterns": ["kubernetes", "k8s"]},
    {"name": "CI/CD", "patterns": ["ci/cd", "cicd"]},
    {"name": "Git", "patterns": ["git"]},
    {"name": "Linux", "patterns": ["linux"]},
    {"name": "REST", "patterns": ["rest", "apis rest", "api rest"]},
    {"name": "SOAP", "patterns": ["soap", "web services soap"]},
    {"name": "GraphQL", "patterns": ["graphql"]},
    {"name": "OpenAPI", "patterns": ["openapi"]},
    {"name": "API Management", "patterns": ["api management"]},
    {"name": "Microsserviços", "patterns": ["microsservicos", "microservices", "microservicos"]},
    {"name": "ETL", "patterns": ["etl"]},
    {"name": "Spark", "patterns": ["spark"]},
    {"name": "Pandas", "patterns": ["pandas"]},
    {"name": "Machine Learning", "patterns": ["machine learning"]},
    {"name": "LLM", "patterns": ["llm"]},
    {"name": "Oracle Integration Cloud", "patterns": ["oracle integration cloud", "oic"]},
    {"name": "Oracle Cloud Infrastructure", "patterns": ["oracle cloud infrastructure", "oci"]},
    {"name": "Arquitetura de Integração", "patterns": ["arquitetura de integracao", "arquitetura de integracoes"]},
    {"name": "Enterprise Integration Patterns", "patterns": ["enterprise integration patterns"]},
    {"name": "Arquitetura Orientada a Eventos", "patterns": ["arquitetura orientada a eventos", "event driven"]},
    {"name": "Mensageria", "patterns": ["mensageria"]},
    {"name": "Kafka", "patterns": ["kafka"]},
    {"name": "RabbitMQ", "patterns": ["rabbitmq"]},
    {"name": "MuleSoft", "patterns": ["mulesoft"]},
    {"name": "OAuth 2.0", "patterns": ["oauth 2.0", "oauth2", "oauth"]},
    {"name": "OpenID Connect", "patterns": ["openid connect"]},
    {"name": "JWT", "patterns": ["jwt"]},
    {"name": "CORS", "patterns": ["cors"]},
    {"name": "TLS/mTLS", "patterns": ["mtls", "tls"]},
    {"name": "Observabilidade", "patterns": ["observabilidade"]},
    {"name": "SAP S/4HANA", "patterns": ["sap s/4hana", "s/4hana", "s4hana"]},
    {"name": "SAP ECC", "patterns": ["sap ecc"]},
    {"name": "SAP Process Orchestration", "patterns": ["sap process orchestration", "sap po", "pi/po", "sap pi"]},
    {"name": "SAP BTP", "patterns": ["sap business technology platform", "sap btp", "btp"]},
    {"name": "SAP Integration Suite", "patterns": ["sap integration suite", "integration suite"]},
    {"name": "RFC", "patterns": ["rfc"]},
    {"name": "BAPI", "patterns": ["bapi"]},
    {"name": "IDoc", "patterns": ["idoc"]},
    {"name": "OData", "patterns": ["odata"]},
    {"name": "TOGAF", "patterns": ["togaf"]},
    {"name": "ArchiMate", "patterns": ["archimate"]},
    {"name": "BPMN", "patterns": ["bpmn"]},
    {"name": "DevSecOps", "patterns": ["devsecops"]},
]

SOFT_SKILLS: list[dict[str, Any]] = [
    {"name": "Comunicação", "patterns": ["comunicacao"]},
    {"name": "Liderança", "patterns": ["lideranca"]},
    {"name": "Liderança Técnica", "patterns": ["lideranca tecnica"]},
    {"name": "Colaboração", "patterns": ["colaboracao", "equipes multidisciplinares", "trabalho em equipe"]},
    {"name": "Proatividade", "patterns": ["proatividade"]},
    {"name": "Autonomia", "patterns": ["autonomia"]},
    {"name": "Organização", "patterns": ["organizacao"]},
    {"name": "Resolução de Problemas", "patterns": ["resolucao de problemas"]},
    {"name": "Pensamento Crítico", "patterns": ["pensamento critico"]},
    {"name": "Pensamento Sistêmico", "patterns": ["pensamento sistemico"]},
    {"name": "Capacidade Analítica", "patterns": ["capacidade analitica"]},
    {"name": "Visão Holística", "patterns": ["visao holistica"]},
    {"name": "Perfil Consultivo", "patterns": ["perfil consultivo", "postura consultiva"]},
    {"name": "Documentação", "patterns": ["documentacao", "capacidade de documentacao"]},
    {"name": "Mentoria", "patterns": ["mentoria"]},
]

DESIRED_MARKERS = [
    "desejavel",
    "diferencial",
    "diferenciais",
    "nice to have",
    "sera um plus",
    "seria bom",
    "preferencialmente",
]

REQUIRED_MARKERS = [
    "obrigatorio",
    "obrigatorios",
    "requerido",
    "essencial",
    "experiencia solida",
    "conhecimento solido",
    "requisitos obrigatorios",
]

# Tokens curtos / ambíguos que precisam de fronteira de palavra.
BOUNDED_PATTERNS = {
    "git",
    "api",
    "rest",
    "soap",
    "sql",
    "aws",
    "gcp",
    "oci",
    "oic",
    "sap",
    "jwt",
    "tls",
    "rfc",
    "etl",
    "llm",
    "k8s",
    "node",
    "java",
}


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _find_pattern_spans(text: str, pattern: str) -> list[tuple[int, int]]:
    normalized_pattern = normalize_text(pattern)
    if not normalized_pattern:
        return []
    if normalized_pattern in BOUNDED_PATTERNS or len(normalized_pattern) <= 3:
        return [(match.start(), match.end()) for match in re.finditer(rf"(?<![a-z0-9]){re.escape(normalized_pattern)}(?![a-z0-9])", text)]
    # Multi-word: allow flexible whitespace/newlines between tokens (PDF line wraps).
    if " " in normalized_pattern:
        parts = [re.escape(part) for part in normalized_pattern.split() if part]
        if parts:
            flex = r"\s+".join(parts)
            return [(match.start(), match.end()) for match in re.finditer(flex, text)]
    spans = []
    start = 0
    while True:
        index = text.find(normalized_pattern, start)
        if index == -1:
            break
        spans.append((index, index + len(normalized_pattern)))
        start = index + len(normalized_pattern)
    return spans


def _pattern_matches(text: str, pattern: str) -> bool:
    return bool(_find_pattern_spans(text, pattern))


def _desired_section_ranges(text: str) -> list[tuple[int, int]]:
    """Intervalos aproximados de seções de diferenciais/desejáveis."""
    headers = list(re.finditer(r"(^|\n)\s*#{0,3}\s*(diferenciais|desejaveis|nice to have)\b", text))
    if not headers:
        return []
    ranges: list[tuple[int, int]] = []
    next_headers = list(re.finditer(r"(^|\n)\s*#{1,3}\s+\S+", text))
    for header in headers:
        start = header.start()
        end = len(text)
        for candidate in next_headers:
            if candidate.start() > start + 5:
                end = candidate.start()
                break
        ranges.append((start, end))
    return ranges


def _in_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def _line_window(text: str, index: int) -> str:
    start = text.rfind("\n", 0, index)
    start = 0 if start == -1 else start + 1
    end = text.find("\n", index)
    end = len(text) if end == -1 else end
    return text[start:end]


def _window_has_marker(text: str, index: int, markers: list[str], *, line_only: bool = False, radius: int = 40) -> bool:
    # Prioriza a mesma linha/bullet para evitar vazar marcadores de itens vizinhos.
    line = _line_window(text, index)
    if any(marker in line for marker in markers):
        return True
    if line_only:
        return False
    window = text[max(0, index - radius) : index + radius]
    return any(marker in window for marker in markers)


def _skill_is_desired(text: str, spans: list[tuple[int, int]], desired_ranges: list[tuple[int, int]]) -> bool:
    """Desired apenas se todas as menções relevantes forem de diferencial/desejável."""
    if not spans:
        return False

    outside = [(start, end) for start, end in spans if not _in_ranges(start, desired_ranges)]
    if not outside:
        return True

    # Menções fora da seção de diferenciais: só é desired se cada uma tiver marcador local
    # (ex.: "SAP ECC, desejável").
    return all(_window_has_marker(text, start, DESIRED_MARKERS, line_only=True) for start, _end in outside)


async def analyse_job(job: dict[str, Any], llm: LLMClient) -> dict[str, Any]:
    system = load_prompt("analyse_job.system.txt")
    prompt = load_prompt(
        "analyse_job.user.txt",
        title=str(job.get("title", "")),
        profile=str(job.get("profile", "")),
        seniority=str(job.get("seniority", "")),
        description=str(job.get("description", "")),
        job_description=str(job.get("job_description", "")),
        ideal_candidate_context=str(job.get("ideal_candidate_context") or ""),
    )
    result = await llm.json_completion(
        system,
        prompt,
        operation="analyse_job",
        job_id=str(job.get("id") or "") or None,
    )
    if result:
        cleaned = normalize_job_analysis(result)
        if (
            cleaned["must_have"]
            or cleaned["core_skills"]
            or cleaned["hard_skills"]
            or cleaned["soft_skills"]
            or cleaned["desired_skills"]
        ):
            cleaned["analysis_version"] = JOB_ANALYSIS_VERSION
            return cleaned

    heuristic = heuristic_job_analysis(job)
    heuristic["analysis_version"] = JOB_ANALYSIS_VERSION
    return heuristic


async def extract_candidate(
    resume_text: str,
    llm: LLMClient,
    *,
    candidate_id: str | None = None,
) -> dict[str, str]:
    system = load_prompt("extract_candidate.system.txt")
    prompt = load_prompt(
        "extract_candidate.user.txt",
        resume_text=resume_text[:12000],
    )
    result = await llm.json_completion(
        system,
        prompt,
        operation="extract_candidate",
        candidate_id=candidate_id,
    )
    if result:
        return {
            "name": str(result.get("name", ""))[:120],
            "city": str(result.get("city", ""))[:120],
            "reported_role": str(result.get("reported_role", ""))[:160],
        }

    return heuristic_candidate_extraction(resume_text)


SCORE_BATCH_SIZE = 12


async def score_candidate(
    job: dict[str, Any],
    candidate: dict[str, Any],
    llm: LLMClient,
    *,
    scoring_model: str | None = None,
) -> dict[str, Any]:
    model = active_scoring_model(scoring_model)
    analysis = normalize_job_analysis(job.get("analysis") or heuristic_job_analysis(job))
    resume_text = str(candidate.get("resume_text", ""))
    resume_excerpt = resume_text[:10000]
    job_id = str(job.get("id") or "") or None
    candidate_id = str(candidate.get("id") or "") or None
    provider_name = getattr(llm, "provider_name", "local")

    if model == "v2":
        return await _score_candidate_v2(
            job,
            candidate,
            analysis,
            resume_excerpt,
            llm,
            job_id=job_id,
            candidate_id=candidate_id,
        )

    skills = flatten_skills(analysis)
    scores, scoring_method, skills_audit = await _score_skills_with_llm(
        skills,
        resume_excerpt,
        llm,
        model="v1",
        return_audit=True,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    scores = _ground_skill_scores_to_resume(scores, resume_excerpt, soft_null=False)
    built = build_score(job, candidate, skills, scores, scoring_method)
    built["scoring_model_version"] = "v1"

    narrative, narrative_audit = await _score_narrative_with_llm(
        job,
        candidate,
        built,
        resume_excerpt,
        llm,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    if not narrative:
        narrative = heuristic_score_narrative(candidate, job, built["final_score"], built["items"])
    else:
        narrative = _reconcile_narrative_with_scores(narrative, built["items"], candidate, job, built["final_score"])
        if not str(narrative.get("verdict") or "").strip():
            fallback = heuristic_score_narrative(candidate, job, built["final_score"], built["items"])
            narrative["verdict"] = fallback["verdict"]
            if not str(narrative.get("profile_summary") or "").strip():
                narrative["profile_summary"] = fallback["profile_summary"]
            if not narrative.get("verdict_label"):
                narrative["verdict_label"] = fallback["verdict_label"]
    score_label = _verdict_label_from_score(built["final_score"])
    llm_label = narrative.get("verdict_label") or score_label
    if built["final_score"] < 50 and llm_label == "recomendado":
        narrative["verdict_label"] = score_label
    elif built["final_score"] >= 75 and llm_label == "nao_recomendado":
        narrative["verdict_label"] = score_label
    elif not narrative.get("verdict_label"):
        narrative["verdict_label"] = score_label
    built.update(narrative)
    usage = aggregate_usage(
        aggregate_usage_from_audits(skills_audit),
        usage_from_audit_payload(narrative_audit),
    )
    built["llm_provider"] = provider_name
    built["audit"] = {
        "scoring_model_version": "v1",
        "job_analysis_version": analysis.get("analysis_version") or analysis.get("version") or 1,
        "job_updated_at": job.get("updated_at"),
        "candidate_updated_at": candidate.get("updated_at"),
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "prompt_versions": PROMPT_VERSIONS,
        "llm_provider": provider_name,
        "llm_model": getattr(llm, "model", None),
        "llm_temperature": getattr(llm, "temperature", None),
        "skills_llm": skills_audit,
        "narrative_llm": narrative_audit,
    }
    if provider_name == "openai" and usage.get("calls"):
        built["audit"]["usage"] = usage
    return built


async def _score_candidate_v2(
    job: dict[str, Any],
    candidate: dict[str, Any],
    analysis: dict[str, Any],
    resume_excerpt: str,
    llm: LLMClient,
    *,
    job_id: str | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    skills = flatten_skills_v2(analysis)
    if not skills:
        # Fallback to flat lists if tiers empty.
        skills = flatten_skills(analysis)
        for skill in skills:
            cat = str(skill.get("category") or "")
            if cat == "Desired skill":
                skill["tier"] = "DIFFERENTIAL"
            elif cat == "Soft skill":
                skill["tier"] = "SOFT"
            else:
                skill["tier"] = "CORE"

    group_map = skill_group_index(analysis)
    for skill in skills:
        if not skill.get("group"):
            skill["group"] = group_map.get(str(skill["name"]).lower(), "")

    scores, scoring_method, skills_audit = await _score_skills_with_llm(
        skills,
        resume_excerpt,
        llm,
        model="v2",
        return_audit=True,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    scores = _ground_skill_scores_to_resume(scores, resume_excerpt, soft_null=True)
    items = _build_scored_items_v2(skills, scores)

    fit = await _score_fit_with_llm(
        job,
        candidate,
        analysis,
        items,
        resume_excerpt,
        llm,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    role_fit = fit.get("role_fit")
    context_fit = fit.get("context_fit")
    provider_name = getattr(llm, "provider_name", "local")

    result = build_v2_score_result(
        job=job,
        candidate=candidate,
        items=items,
        method=scoring_method,
        role_fit=role_fit,
        context_fit=context_fit,
        skill_groups=analysis.get("skill_groups") or [],
        strengths=fit.get("strengths"),
        interview_validation=fit.get("interview_validation"),
        narrative={},
        audit={
            "scoring_model_version": "v2",
            "job_analysis_version": analysis.get("analysis_version") or analysis.get("version") or JOB_ANALYSIS_VERSION,
            "job_updated_at": job.get("updated_at"),
            "candidate_updated_at": candidate.get("updated_at"),
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "prompt_versions": PROMPT_VERSIONS,
            "llm_provider": provider_name,
            "llm_model": getattr(llm, "model", None),
            "llm_temperature": getattr(llm, "temperature", None),
            "skills_llm": skills_audit,
            "fit_llm": fit.get("audit"),
        },
    )

    narrative, narrative_audit = await _score_narrative_with_llm(
        job,
        candidate,
        result,
        resume_excerpt,
        llm,
        model="v2",
        job_id=job_id,
        candidate_id=candidate_id,
    )
    if not narrative:
        narrative = heuristic_score_narrative_v2(candidate, job, result)
    else:
        narrative = _reconcile_narrative_with_scores(
            narrative, result["items"], candidate, job, result["final_score"]
        )
        # Keep backend verdict_label; enrich text only.
        if not str(narrative.get("verdict") or "").strip():
            fallback = heuristic_score_narrative_v2(candidate, job, result)
            narrative["verdict"] = fallback["verdict"]
        if not str(narrative.get("profile_summary") or "").strip():
            fallback = heuristic_score_narrative_v2(candidate, job, result)
            narrative["profile_summary"] = fallback["profile_summary"]

    result["profile_summary"] = narrative.get("profile_summary", "")
    result["verdict"] = narrative.get("verdict", "")
    result["llm_provider"] = provider_name
    result.setdefault("audit", {})
    result["audit"]["narrative_llm"] = narrative_audit
    usage = aggregate_usage(
        aggregate_usage_from_audits(skills_audit),
        usage_from_audit_payload(fit.get("audit")),
        usage_from_audit_payload(narrative_audit),
    )
    if provider_name == "openai" and usage.get("calls"):
        result["audit"]["usage"] = usage
    # Backend decides verdict_label (LLM interprets narrative only).
    if not result.get("interview_validation") and fit.get("interview_validation"):
        result["interview_validation"] = fit["interview_validation"]
    if fit.get("strengths"):
        result["strengths"] = fit["strengths"]
    if fit.get("gaps"):
        # Prefer structured critical gaps names when present.
        result["gaps"] = fit["gaps"]
    return result


def _build_scored_items_v2(
    skills: list[dict[str, Any]],
    scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    score_by_name = {normalize_text(item["name"]): item for item in scores}
    rows: list[dict[str, Any]] = []
    for skill in skills:
        key = normalize_text(str(skill["name"]))
        score_item = score_by_name.get(key, {})
        score = score_item.get("score")
        weight = float(skill.get("weight", 1))
        evidence = score_item.get("evidence") or []
        if isinstance(evidence, str):
            evidence = normalize_evidence_list(evidence)
        status = score_item.get("evidence_status") or normalize_evidence_status(
            None, score=score if isinstance(score, int) else None, is_soft=is_soft_skill(skill)
        )
        confidence = score_item.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else (
                0.8 if status == "explicit" else 0.3 if status == "inferred" else 0.1
            )
        except (TypeError, ValueError):
            confidence = 0.1

        weighted_score = None
        if score is not None:
            weighted_score = round(float(score) * weight, 2)

        rows.append(
            {
                "category": skill.get("category", ""),
                "name": skill["name"],
                "weight": int(weight) if float(weight).is_integer() else weight,
                "tier": skill.get("tier") or "",
                "group": skill.get("group") or "",
                "score": score,
                "confidence": round(confidence, 3),
                "evidence_status": status,
                "evidence": evidence,
                "weighted_score": weighted_score,
                # Legacy single-string evidence for templates/charts that expect it.
                "evidence_text": evidence_to_legacy_text(evidence, status),
            }
        )
    return rows


async def _score_fit_with_llm(
    job: dict[str, Any],
    candidate: dict[str, Any],
    analysis: dict[str, Any],
    items: list[dict[str, Any]],
    resume_text: str,
    llm: LLMClient,
    *,
    job_id: str | None = None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    must = [i["name"] for i in items if str(i.get("tier") or "").upper() == "MUST_HAVE"]
    scored_lines = []
    for item in items:
        score = item.get("score")
        score_label = "n/a" if score is None else f"{score}/5"
        scored_lines.append(
            f"- {item.get('name')} [{item.get('tier')}] {score_label} "
            f"status={item.get('evidence_status')} | {item.get('evidence_text') or 'n/d'}"
        )
    system = load_prompt("score_fit.system.txt")
    prompt = load_prompt(
        "score_fit.user.txt",
        job_title=str(job.get("title", "")),
        job_profile=str(job.get("profile", "")),
        job_seniority=str(job.get("seniority", "")),
        role_intent=str(analysis.get("role_intent") or ""),
        role_expectations=str(analysis.get("role_expectations") or ""),
        context_signals=", ".join(analysis.get("context_signals") or []) or "(nenhum)",
        ideal_candidate_context=str(job.get("ideal_candidate_context") or "")[:2000],
        must_have=", ".join(must) or "(nenhum)",
        scored_skills="\n".join(scored_lines) or "- (nenhuma)",
        resume_text=resume_text[:6000],
        candidate_role=str(candidate.get("reported_role") or ""),
        candidate_city=str(candidate.get("city") or ""),
    )
    audit_payload = await llm.json_completion_with_audit(
        system,
        prompt,
        timeout=max(llm.timeout, 120),
        operation="score_fit",
        job_id=job_id,
        candidate_id=candidate_id,
    )
    parsed = (audit_payload or {}).get("parsed") or {}
    cleaned = _clean_fit_payload(parsed, items)
    cleaned["audit"] = {
        "raw": (audit_payload or {}).get("raw", "")[:8000],
        "model": (audit_payload or {}).get("model"),
        "provider": (audit_payload or {}).get("provider"),
        "temperature": (audit_payload or {}).get("temperature"),
        "error": (audit_payload or {}).get("error"),
        "attempts": (audit_payload or {}).get("attempts"),
        "prompt_tokens": (audit_payload or {}).get("prompt_tokens"),
        "completion_tokens": (audit_payload or {}).get("completion_tokens"),
        "total_tokens": (audit_payload or {}).get("total_tokens"),
        "estimated_cost_usd": (audit_payload or {}).get("estimated_cost_usd"),
    }
    return cleaned


def _clean_fit_payload(result: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    def _pct(key: str, *aliases: str) -> float | None:
        for name in (key, *aliases):
            if name in result and result.get(name) is not None:
                try:
                    return max(0.0, min(100.0, float(result.get(name))))
                except (TypeError, ValueError):
                    continue
        return None

    role_fit = _pct("role_fit", "roleFit", "seniority_fit")
    context_fit = _pct("context_fit", "contextFit", "professional_context_fit")
    if role_fit is None:
        role_fit = _heuristic_role_fit(items)
    if context_fit is None:
        context_fit = 50.0

    strengths = result.get("strengths") or result.get("pontos_fortes") or []
    gaps = result.get("gaps") or result.get("lacunas") or []
    interview = (
        result.get("interview_validation")
        or result.get("interview_questions")
        or result.get("perguntas_entrevista")
        or []
    )
    if not isinstance(strengths, list):
        strengths = []
    if not isinstance(gaps, list):
        gaps = []
    if not isinstance(interview, list):
        interview = []

    return {
        "role_fit": role_fit,
        "context_fit": context_fit,
        "strengths": [str(s)[:160] for s in strengths if str(s).strip()][:10],
        "gaps": [str(s)[:160] for s in gaps if str(s).strip()][:10],
        "interview_validation": [str(s)[:240] for s in interview if str(s).strip()][:10],
    }


def _heuristic_role_fit(items: list[dict[str, Any]]) -> float:
    arch_markers = ("arquitet", "lideran", "tech lead", "solu")
    soft = [i for i in items if str(i.get("tier") or "").upper() == "SOFT"]
    scores = [float(i["score"]) for i in soft if i.get("score") is not None]
    if scores:
        return round(sum(scores) / len(scores) / 5 * 100, 2)
    must = [i for i in items if str(i.get("tier") or "").upper() == "MUST_HAVE" and i.get("score") is not None]
    if must:
        return round(sum(float(i["score"]) for i in must) / len(must) / 5 * 100, 2)
    return 50.0


def heuristic_score_narrative_v2(
    candidate: dict[str, Any],
    job: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, str]:
    name = str(candidate.get("name") or "Candidato").strip() or "Candidato"
    job_title = str(job.get("title") or "a vaga").strip()
    final_score = result.get("final_score", 0)
    label = result.get("verdict_label") or decide_verdict(
        final_score=float(final_score),
        must_have_coverage=result.get("must_have_coverage") or {},
        critical_gaps=result.get("critical_gaps") or [],
        role_fit=result.get("role_fit"),
    )
    strengths = result.get("strengths") or []
    gaps = result.get("gaps") or []
    coverage = result.get("must_have_coverage") or {}
    profile_summary = (
        f"{name}. Avaliação v2 para {job_title}: score {final_score}%. "
        f"Must-haves {coverage.get('covered', 0)}/{coverage.get('total', 0)}."
    )
    if strengths:
        profile_summary += f" Pontos fortes: {', '.join(strengths[:5])}."
    if gaps:
        profile_summary += f" Lacunas: {', '.join(gaps[:5])}."

    verdict_text = {
        "strong_fit": f"Veredito: forte aderência (strong_fit) para {job_title} com score {final_score}%.",
        "recommended": f"Veredito: recomendado para {job_title} com score {final_score}%.",
        "evaluate": (
            f"Veredito: avaliar com validação (evaluate) para {job_title}. "
            f"Score {final_score}% — aprofundar must-haves e gaps críticos em entrevista."
        ),
        "not_recommended": (
            f"Veredito: não recomendado para {job_title} neste momento (score {final_score}%)."
        ),
    }.get(label, f"Veredito: {label} — score {final_score}%.")

    return {
        "profile_summary": profile_summary[:1200],
        "verdict": verdict_text[:1200],
        "verdict_label": label,
    }


async def _score_skills_with_llm(
    skills: list[dict[str, Any]],
    resume_text: str,
    llm: LLMClient,
    *,
    model: str = "v1",
    return_audit: bool = False,
    job_id: str | None = None,
    candidate_id: str | None = None,
) -> Any:
    if not skills:
        empty = ([], "heuristic", []) if return_audit else ([], "heuristic")
        return empty

    system = load_prompt("score_skills.system.txt")
    merged: list[dict[str, Any]] = []
    llm_batches = 0
    audits: list[dict[str, Any]] = []

    for batch in _chunked(skills, SCORE_BATCH_SIZE):
        soft_flags = "\n".join(
            f"- {skill['name']}" + (" [soft]" if is_soft_skill(skill) else " [tech]")
            for skill in batch
        )
        prompt = load_prompt(
            "score_skills.user.txt",
            skills=soft_flags,
            resume_text=resume_text,
        )
        audit_payload = await llm.json_completion_with_audit(
            system,
            prompt,
            timeout=max(llm.timeout, 120),
            operation="score_skills",
            job_id=job_id,
            candidate_id=candidate_id,
        )
        result = (audit_payload or {}).get("parsed")
        cleaned = _clean_skill_scores(result, batch, model=model)
        if _skill_scores_are_usable(cleaned, result):
            merged.extend(cleaned)
            llm_batches += 1
        else:
            merged.extend(heuristic_skill_scores(batch, resume_text, model=model))
        if return_audit:
            audits.append(
                {
                    "raw": (audit_payload or {}).get("raw", "")[:4000],
                    "model": (audit_payload or {}).get("model"),
                    "provider": (audit_payload or {}).get("provider"),
                    "temperature": (audit_payload or {}).get("temperature"),
                    "error": (audit_payload or {}).get("error"),
                    "attempts": (audit_payload or {}).get("attempts"),
                    "prompt_tokens": (audit_payload or {}).get("prompt_tokens"),
                    "completion_tokens": (audit_payload or {}).get("completion_tokens"),
                    "total_tokens": (audit_payload or {}).get("total_tokens"),
                    "estimated_cost_usd": (audit_payload or {}).get("estimated_cost_usd"),
                    "usable": bool(_skill_scores_are_usable(cleaned, result)),
                }
            )

    if llm_batches == 0:
        scores = heuristic_skill_scores(skills, resume_text, model=model)
        method = "heuristic"
    else:
        scores = merged
        total_batches = len(_chunked(skills, SCORE_BATCH_SIZE))
        method = "hybrid" if llm_batches < total_batches else "llm"

    if return_audit:
        return scores, method, audits
    return scores, method


async def _score_narrative_with_llm(
    job: dict[str, Any],
    candidate: dict[str, Any],
    built: dict[str, Any],
    resume_text: str,
    llm: LLMClient,
    *,
    model: str = "v1",
    job_id: str | None = None,
    candidate_id: str | None = None,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    items = built.get("items", [])
    scored_lines = []
    for item in items:
        score = item.get("score")
        score_label = "n/a" if score is None else f"{score}/5"
        evidence = item.get("evidence_text") or item.get("evidence") or "n/d"
        if isinstance(evidence, list):
            evidence = evidence_to_legacy_text(evidence, str(item.get("evidence_status") or ""))
        scored_lines.append(
            f"- {item.get('name')}: {score_label} (peso {item.get('weight')})"
            f" | evidência: {evidence}"
        )
    strengths, gaps = _partition_strengths_and_gaps(items)
    system = load_prompt("score_narrative.system.txt")
    verdict_hint = (
        "strong_fit|recommended|evaluate|not_recommended"
        if model == "v2"
        else "recomendado|considerar|nao_recomendado"
    )
    prompt = load_prompt(
        "score_narrative.user.txt",
        job_title=str(job.get("title", "")),
        job_profile=str(job.get("profile", "")),
        job_seniority=str(job.get("seniority", "")),
        job_description=str(job.get("job_description") or job.get("description") or "")[:2500],
        final_score=str(built.get("final_score", 0)),
        scored_skills="\n".join(scored_lines) or "- (nenhuma)",
        strengths_list="\n".join(f"- {name}" for name in strengths) or "- (nenhum)",
        gaps_list="\n".join(f"- {name}" for name in gaps) or "- (nenhuma)",
        resume_text=resume_text[:6000],
        verdict_labels=verdict_hint,
        must_have_coverage=str(
            (built.get("must_have_coverage") or {}).get("ratio", "")
            if model == "v2"
            else ""
        ),
        scoring_model=model,
    )
    audit_payload = await llm.json_completion_with_audit(
        system,
        prompt,
        timeout=max(llm.timeout, 120),
        operation="score_narrative",
        job_id=job_id,
        candidate_id=candidate_id,
    )
    result = (audit_payload or {}).get("parsed") or {}
    narrative = _clean_score_narrative(result, model=model)
    return narrative, audit_payload


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _extract_skills_payload(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    raw = None
    for key in ("skills", "habilidades", "scores", "items", "avaliacoes", "avaliações"):
        if key in result:
            raw = result.get(key)
            break
    if raw is None:
        # Alguns modelos devolvem a lista na raiz sob chaves numéricas / mapa nome→nota.
        if all(isinstance(value, (dict, int, float, str)) for value in result.values()):
            maybe_map = {
                key: value
                for key, value in result.items()
                if key
                not in {
                    "profile_summary",
                    "verdict",
                    "verdict_label",
                    "resumo",
                    "veredito",
                }
            }
            if maybe_map and any(isinstance(v, (dict, int, float)) for v in maybe_map.values()):
                raw = maybe_map

    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]

    if isinstance(raw, dict):
        items: list[dict[str, Any]] = []
        for name, payload in raw.items():
            if isinstance(payload, dict):
                item = dict(payload)
                item.setdefault("name", name)
                items.append(item)
            else:
                items.append({"name": str(name), "score": payload, "evidence": ""})
        return items

    return []


def _skill_scores_are_usable(cleaned: list[dict[str, Any]], raw_result: dict[str, Any] | None) -> bool:
    if not cleaned:
        return False
    if not _extract_skills_payload(raw_result):
        return False
    missing = sum(1 for item in cleaned if item.get("evidence") == "Sem avaliação da LLM.")
    # Aceita o lote se a maioria das habilidades veio da LLM.
    return missing <= max(1, len(cleaned) // 3)


def heuristic_score_narrative(
    candidate: dict[str, Any],
    job: dict[str, Any],
    final_score: float,
    items: list[dict[str, Any]],
) -> dict[str, str]:
    name = str(candidate.get("name") or "Candidato").strip() or "Candidato"
    role = str(candidate.get("reported_role") or "").strip()
    city = str(candidate.get("city") or "").strip()
    job_title = str(job.get("title") or "a vaga").strip()

    strengths = [item["name"] for item in items if item.get("score", 0) >= 4][:5]
    gaps = [item["name"] for item in items if item.get("score", 0) <= 1][:5]

    profile_bits = [f"{name}"]
    if role:
        profile_bits.append(f"atua ou reporta experiência como {role}")
    if city:
        profile_bits.append(f"com base em {city}")
    profile_summary = (
        f"{', '.join(profile_bits)}. "
        f"Avaliação automática de aderência à vaga {job_title} resultou em score {final_score}%."
    )
    if strengths:
        profile_summary += f" Pontos com boa evidência: {', '.join(strengths)}."
    if gaps:
        profile_summary += f" Lacunas ou baixa evidência em: {', '.join(gaps)}."

    verdict_label = _verdict_label_from_score(final_score)
    if verdict_label == "recomendado":
        verdict = (
            f"Veredito: recomendado para {job_title}. "
            f"O score de {final_score}% indica aderência consistente aos critérios ponderados."
        )
    elif verdict_label == "considerar":
        verdict = (
            f"Veredito: considerar com ressalvas para {job_title}. "
            f"O score de {final_score}% mostra aderência parcial; vale aprofundar entrevistas nos gaps identificados."
        )
    else:
        verdict = (
            f"Veredito: não recomendado para {job_title} neste momento. "
            f"O score de {final_score}% indica desalinhamento relevante frente aos requisitos principais."
        )

    return {
        "profile_summary": profile_summary[:1200],
        "verdict": verdict[:1200],
        "verdict_label": verdict_label,
    }


def _verdict_label_from_score(final_score: float) -> str:
    return verdict_label_v1_from_score(final_score)


def _clean_score_narrative(result: dict[str, Any], *, model: str = "v1") -> dict[str, str]:
    label = normalize_text(
        str(result.get("verdict_label") or result.get("label") or result.get("recomendacao") or "")
    )
    if model == "v2":
        allowed = {
            "strong_fit": "strong_fit",
            "forte": "strong_fit",
            "recommended": "recommended",
            "recomendado": "recommended",
            "evaluate": "evaluate",
            "considerar": "evaluate",
            "avaliar": "evaluate",
            "not_recommended": "not_recommended",
            "nao_recomendado": "not_recommended",
            "nao recomendado": "not_recommended",
            "não recomendado": "not_recommended",
        }
    else:
        allowed = {
            "recomendado": "recomendado",
            "considerar": "considerar",
            "nao_recomendado": "nao_recomendado",
            "nao recomendado": "nao_recomendado",
            "não recomendado": "nao_recomendado",
            "reject": "nao_recomendado",
            "recommended": "recomendado",
            "consider": "considerar",
            "evaluate": "considerar",
            "strong_fit": "recomendado",
            "not_recommended": "nao_recomendado",
        }
    verdict_label = allowed.get(label, "")
    profile_summary = str(
        result.get("profile_summary") or result.get("resumo") or result.get("resumo_perfil") or ""
    ).strip()
    verdict = str(result.get("verdict") or result.get("veredito") or "").strip()
    if not profile_summary and not verdict:
        return {}
    default_label = "evaluate" if model == "v2" else "considerar"
    return {
        "profile_summary": profile_summary[:1200],
        "verdict": verdict[:1200],
        "verdict_label": verdict_label or default_label,
    }

def heuristic_job_analysis(job: dict[str, Any]) -> dict[str, Any]:
    raw_text = " ".join(str(job.get(field, "")) for field in ["title", "description", "job_description"])
    text = normalize_text(raw_text)
    desired_ranges = _desired_section_ranges(text)
    hard: list[dict[str, Any]] = []
    desired: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Preferir padrões mais longos/específicos primeiro.
    ordered = sorted(
        TECH_SKILLS,
        key=lambda item: max((len(normalize_text(p)) for p in item["patterns"]), default=0),
        reverse=True,
    )

    for skill in ordered:
        spans: list[tuple[int, int]] = []
        matched_pattern = ""
        for pattern in skill["patterns"]:
            found = _find_pattern_spans(text, pattern)
            if found:
                spans = found
                matched_pattern = pattern
                break
        if not spans:
            continue

        name = skill["name"]
        key = normalize_text(name)
        if key in seen:
            continue
        # Evita genéricos quando um termo mais específico já foi capturado
        # (ex.: "Azure" depois de "Azure Integration Services").
        if any(key != existing and (key in existing or existing in key) for existing in seen):
            continue

        item = {"name": name, "weight": infer_weight(text, matched_pattern or name)}
        if _skill_is_desired(text, spans, desired_ranges):
            item["weight"] = min(item["weight"], 2)
            desired.append(item)
        else:
            hard.append(item)
        seen.add(key)

    soft = []
    for skill in SOFT_SKILLS:
        if any(_pattern_matches(text, pattern) for pattern in skill["patterns"]):
            soft.append({"name": skill["name"], "weight": infer_weight(text, skill["patterns"][0])})

    if not hard:
        hard = [{"name": "Experiência Técnica Compatível", "weight": 4}]
    if not soft:
        soft = [{"name": "Comunicação", "weight": 3}, {"name": "Colaboração", "weight": 3}]

    return normalize_job_analysis(
        {"hard_skills": hard[:20], "soft_skills": soft[:12], "desired_skills": desired[:12]}
    )


def heuristic_candidate_extraction(resume_text: str) -> dict[str, str]:
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    name = lines[0][:120] if lines else ""
    city = ""
    reported_role = ""

    city_match = re.search(r"(cidade|localidade|location)\s*[:\-]\s*(.+)", resume_text, flags=re.I)
    if city_match:
        city = city_match.group(2).splitlines()[0][:120].strip()

    role_match = re.search(r"(cargo|fun[cç][aã]o|role|position)\s*[:\-]\s*(.+)", resume_text, flags=re.I)
    if role_match:
        reported_role = role_match.group(2).splitlines()[0][:160].strip()
    elif len(lines) > 1:
        reported_role = lines[1][:160]

    return {"name": name, "city": city, "reported_role": reported_role}


def _skill_match_patterns(skill_name: str) -> list[str]:
    """Padrões canônicos do catálogo; fallback = frase completa (nunca tokens soltos)."""
    expected = normalize_text(skill_name)
    for catalog in (TECH_SKILLS, SOFT_SKILLS):
        for skill in catalog:
            if normalize_text(skill["name"]) == expected:
                return list(skill["patterns"])
    return [skill_name] if skill_name.strip() else []


def _tech_skill_patterns(skill_name: str) -> list[str] | None:
    expected = normalize_text(skill_name)
    for skill in TECH_SKILLS:
        if normalize_text(skill["name"]) == expected:
            return list(skill["patterns"])
    return None


def heuristic_skill_scores(
    skills: list[dict[str, Any]],
    resume_text: str,
    *,
    model: str = "v1",
) -> list[dict[str, Any]]:
    """Pontua por frase/padrão completo — não soma tokens isolados (evita OIC via 'cloud'+'integration')."""
    text = normalize_text(resume_text)
    scored = []
    for skill in skills:
        skill_name = str(skill["name"])
        soft = is_soft_skill(skill)
        patterns = _skill_match_patterns(skill_name)
        hit_count = 0
        for pattern in patterns:
            hit_count += len(_find_pattern_spans(text, pattern))
        if hit_count <= 0:
            score: int | None = None if (model == "v2" and soft) else 0
            status = "needs_validation" if (model == "v2" and soft) else "not_found"
            evidence = [] if model == "v2" else "Sem evidência textual no currículo."
        elif hit_count == 1:
            score = 3
            status = "explicit"
            evidence = (
                [{"text": "Menções encontradas no currículo.", "source": "resume"}]
                if model == "v2"
                else "Menções encontradas no currículo."
            )
        elif hit_count <= 3:
            score = 4
            status = "explicit"
            evidence = (
                [{"text": "Menções encontradas no currículo.", "source": "resume"}]
                if model == "v2"
                else "Menções encontradas no currículo."
            )
        else:
            score = 5
            status = "explicit"
            evidence = (
                [{"text": "Menções encontradas no currículo.", "source": "resume"}]
                if model == "v2"
                else "Menções encontradas no currículo."
            )

        if model == "v2":
            scored.append(
                {
                    "name": skill_name,
                    "score": score,
                    "confidence": 0.75 if status == "explicit" else 0.15,
                    "evidence_status": status,
                    "evidence": evidence if isinstance(evidence, list) else normalize_evidence_list(evidence),
                }
            )
        else:
            scored.append(
                {
                    "name": skill_name,
                    "score": int(score or 0),
                    "evidence": evidence if isinstance(evidence, str) else evidence_to_legacy_text(evidence, status),
                }
            )
    return scored


def _ground_skill_scores_to_resume(
    scores: list[dict[str, Any]],
    resume_text: str,
    *,
    soft_null: bool = False,
) -> list[dict[str, Any]]:
    """Ajusta hard skills de catálogo: zera sem evidência; sobe piso mínimo se o padrão bater."""
    text = normalize_text(resume_text)
    grounded: list[dict[str, Any]] = []
    soft_names = {normalize_text(s["name"]) for s in SOFT_SKILLS}

    for item in scores:
        name = str(item.get("name", ""))
        raw_score = item.get("score")
        score: int | None
        if raw_score is None:
            score = None
        else:
            try:
                score = int(float(raw_score))
            except (TypeError, ValueError):
                score = 0

        evidence_raw = item.get("evidence")
        if isinstance(evidence_raw, list):
            evidence_list = normalize_evidence_list(evidence_raw)
            evidence = evidence_to_legacy_text(evidence_list, str(item.get("evidence_status") or ""))
        else:
            evidence = str(evidence_raw or "").strip()
            evidence_list = normalize_evidence_list(evidence)

        soft = is_soft_skill(item) or normalize_text(name) in soft_names
        if soft_null and soft and (score is None or score == 0) and not _soft_pattern_hit(name, text):
            grounded.append(
                {
                    "name": name,
                    "score": None,
                    "confidence": float(item.get("confidence") or 0.1),
                    "evidence_status": "needs_validation",
                    "evidence": [],
                }
            )
            continue

        patterns = _tech_skill_patterns(name)
        if patterns is None:
            if soft_null:
                status = normalize_evidence_status(
                    item.get("evidence_status"), score=score, is_soft=soft
                )
                grounded.append(
                    {
                        "name": name,
                        "score": score,
                        "confidence": item.get("confidence", 0.5),
                        "evidence_status": status,
                        "evidence": evidence_list,
                    }
                )
            else:
                grounded.append(item)
            continue

        hit_count = sum(len(_find_pattern_spans(text, pattern)) for pattern in patterns)
        pattern_hit = hit_count > 0
        evidence_norm = normalize_text(evidence)
        evidence_in_resume = (
            len(evidence_norm) >= 24
            and evidence_norm
            not in {
                "mencoes encontradas no curriculo.",
                "evidencia identificada no curriculo pela llm.",
                "sem evidencia textual no curriculo.",
                "sem avaliacao da llm.",
                "sem avaliacao.",
                "sem evidencia textual; validar em entrevista.",
            }
            and evidence_norm in text
        )

        if score is not None and score > 0 and not pattern_hit and not evidence_in_resume:
            if soft_null:
                grounded.append(
                    {
                        "name": name,
                        "score": 0,
                        "confidence": 0.2,
                        "evidence_status": "not_found",
                        "evidence": [],
                    }
                )
            else:
                grounded.append(
                    {
                        "name": name,
                        "score": 0,
                        "evidence": "Sem evidência textual no currículo.",
                    }
                )
            continue

        if (score is None or score == 0) and pattern_hit:
            floor = 3 if hit_count == 1 else 4 if hit_count <= 3 else 5
            if soft_null:
                grounded.append(
                    {
                        "name": name,
                        "score": floor,
                        "confidence": 0.7,
                        "evidence_status": "explicit",
                        "evidence": [{"text": "Menções encontradas no currículo.", "source": "resume"}],
                    }
                )
            else:
                grounded.append(
                    {
                        "name": name,
                        "score": floor,
                        "evidence": "Menções encontradas no currículo.",
                    }
                )
            continue

        if soft_null:
            status = normalize_evidence_status(
                item.get("evidence_status"), score=score if score is not None else 0, is_soft=False
            )
            grounded.append(
                {
                    "name": name,
                    "score": 0 if score is None else score,
                    "confidence": item.get("confidence", 0.6),
                    "evidence_status": status,
                    "evidence": evidence_list,
                }
            )
        else:
            grounded.append(item)
    return grounded


def _soft_pattern_hit(skill_name: str, normalized_resume: str) -> bool:
    for skill in SOFT_SKILLS:
        if normalize_text(skill["name"]) == normalize_text(skill_name):
            return any(_pattern_matches(normalized_resume, p) for p in skill["patterns"])
    return False


def _partition_strengths_and_gaps(
    items: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    strengths = []
    gaps = []
    for item in items:
        score = item.get("score")
        if score is None:
            continue
        value = int(score or 0)
        if value >= 3:
            strengths.append(str(item["name"]))
        elif value <= 1:
            gaps.append(str(item["name"]))
    return strengths, gaps


def _narrative_claims_gap_skills(text: str, gap_names: list[str]) -> list[str]:
    """Detecta atribuição positiva de skills com score baixo (ignora menção como lacuna)."""
    if not text or not gap_names:
        return []
    normalized = normalize_text(text)
    negative_markers = (
        "lacuna",
        "lacunas",
        "falta",
        "sem experiencia",
        "sem evidencia",
        "ausencia",
        "nao possui",
        "nao tem",
        "baixa evidencia",
        "sem conhecimento",
        "gap",
        "desconhece",
        "nao demonstra",
        "nao apresenta",
        "limitad",
        "apesar da falta",
    )
    positive_markers = (
        "forte experiencia",
        "experiencia em",
        "experiencia com",
        "experiencia no",
        "experiencia na",
        "expertise",
        "especializad",
        "dominio em",
        "dominio no",
        "solido conhecimento",
        "especialmente no",
        "especialmente em",
        "habilidade em",
        "habilidades em",
        "proficien",
        "atuacao em",
        "atuacao com",
        "conhecimento em",
        "conhecimento solido",
        "forte expertise",
    )
    claimed: list[str] = []
    for name in gap_names:
        aliases = [name, *_skill_match_patterns(name)]
        found_positive = False
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if len(alias_norm) < 3:
                continue
            start = 0
            while True:
                index = normalized.find(alias_norm, start)
                if index == -1:
                    break
                window = normalized[max(0, index - 56) : index + len(alias_norm) + 28]
                has_negative = any(marker in window for marker in negative_markers)
                has_positive = any(marker in window for marker in positive_markers)
                if has_positive and not has_negative:
                    found_positive = True
                    break
                start = index + len(alias_norm)
            if found_positive:
                break
        if found_positive:
            claimed.append(name)
    return claimed


def _reconcile_narrative_with_scores(
    narrative: dict[str, str],
    items: list[dict[str, Any]],
    candidate: dict[str, Any],
    job: dict[str, Any],
    final_score: float,
) -> dict[str, str]:
    """Se o texto citar skill com score baixo como experiência, substitui pelo fallback factual."""
    _, gaps = _partition_strengths_and_gaps(items)
    if not gaps:
        return narrative
    combined = f"{narrative.get('profile_summary', '')}\n{narrative.get('verdict', '')}"
    if not _narrative_claims_gap_skills(combined, gaps):
        return narrative
    fallback = heuristic_score_narrative(candidate, job, final_score, items)
    label = narrative.get("verdict_label") or fallback["verdict_label"]
    return {
        "profile_summary": fallback["profile_summary"],
        "verdict": fallback["verdict"],
        "verdict_label": label,
    }


def build_score(
    job: dict[str, Any],
    candidate: dict[str, Any],
    skills: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    method: str,
) -> dict[str, Any]:
    score_by_name = {item["name"].lower(): item for item in scores}
    rows = []
    weighted_points = 0.0
    max_points = 0.0

    for skill in skills:
        weight = float(skill.get("weight", 1))
        score_item = score_by_name.get(str(skill["name"]).lower(), {"score": 0, "evidence": "Sem avaliação."})
        raw = score_item.get("score")
        if raw is None:
            # v1 never excludes soft skills from denominator.
            score = 0
        else:
            score = max(0, min(5, int(raw)))
        weighted_points += score * weight
        max_points += 5 * weight
        evidence = score_item.get("evidence", "")
        if isinstance(evidence, list):
            evidence = evidence_to_legacy_text(
                evidence, str(score_item.get("evidence_status") or "")
            )
        rows.append(
            {
                "category": skill.get("category", ""),
                "name": skill["name"],
                "weight": int(weight),
                "score": score,
                "weighted_score": round(score * weight, 2),
                "evidence": evidence,
            }
        )

    final_score = round((weighted_points / max_points) * 100, 2) if max_points else 0
    return {
        "job_id": job["id"],
        "candidate_id": candidate["id"],
        "job_title": job.get("title", ""),
        "candidate_name": candidate.get("name", ""),
        "final_score": final_score,
        "method": method,
        "scoring_model_version": "v1",
        "items": rows,
        "profile_summary": "",
        "verdict": "",
        "verdict_label": _verdict_label_from_score(final_score),
    }


def build_score_chart_data(items: list[dict[str, Any]], *, max_skill_axes: int = 8) -> dict[str, Any]:
    """Monta séries esperado vs candidato para radar/barras."""
    category_order = [
        "Must-have",
        "Core skill",
        "Supporting skill",
        "Hard skill",
        "Soft skill",
        "Differential",
        "Desired skill",
    ]
    category_labels = {
        "Must-have": "Must-have",
        "Core skill": "Core",
        "Supporting skill": "Supporting",
        "Hard skill": "Hard skills",
        "Soft skill": "Soft skills",
        "Differential": "Differentials",
        "Desired skill": "Desired skills",
    }

    by_category: dict[str, list[dict[str, Any]]] = {key: [] for key in category_order}
    for item in items:
        category = str(item.get("category") or "Hard skill")
        by_category.setdefault(category, []).append(item)

    category_labels_out: list[str] = []
    expected_category: list[float] = []
    candidate_category: list[float] = []
    for category in category_order:
        rows = by_category.get(category) or []
        if not rows:
            continue
        evaluable = [row for row in rows if row.get("score") is not None]
        if not evaluable:
            continue
        max_points = sum(5 * float(row.get("weight", 1)) for row in evaluable)
        got_points = sum(float(row.get("score", 0)) * float(row.get("weight", 1)) for row in evaluable)
        pct = round((got_points / max_points) * 100, 1) if max_points else 0.0
        category_labels_out.append(category_labels.get(category, category))
        expected_category.append(100.0)
        candidate_category.append(pct)

    ranked = sorted(
        [row for row in items if row.get("score") is not None],
        key=lambda row: (-float(row.get("weight", 1)), -float(row.get("score", 0)), str(row.get("name", ""))),
    )
    skill_rows = ranked[:max_skill_axes]
    skill_labels = [str(row.get("name", ""))[:28] for row in skill_rows]
    expected_skills = [5.0 for _ in skill_rows]
    candidate_skills = [float(row.get("score", 0)) for row in skill_rows]

    breakdown = None
    return {
        "category": {
            "labels": category_labels_out,
            "expected": expected_category,
            "candidate": candidate_category,
            "max": 100,
            "unit": "%",
        },
        "skills": {
            "labels": skill_labels,
            "expected": expected_skills,
            "candidate": candidate_skills,
            "max": 5,
            "unit": "nota",
        },
        "breakdown": breakdown,
    }


def flatten_skills(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "hard_skills": "Hard skill",
        "soft_skills": "Soft skill",
        "desired_skills": "Desired skill",
    }
    analysis = normalize_job_analysis(analysis)
    skills = []
    for key, label in labels.items():
        for item in analysis.get(key, []):
            skills.append(
                {
                    "category": label,
                    "name": item["name"],
                    "weight": item.get("weight", 1),
                    "tier": item.get("tier") or (
                        "SOFT"
                        if key == "soft_skills"
                        else "DIFFERENTIAL"
                        if key == "desired_skills"
                        else "CORE"
                    ),
                    "group": item.get("group") or "",
                }
            )
    return skills


def infer_weight(text: str, skill: str) -> int:
    spans = _find_pattern_spans(text, skill)
    if not spans:
        return 2
    # Usa a primeira menção fora de seção de diferenciais, se houver.
    desired_ranges = _desired_section_ranges(text)
    preferred = next((start for start, _ in spans if not _in_ranges(start, desired_ranges)), spans[0][0])
    if _window_has_marker(text, preferred, REQUIRED_MARKERS + ["forte", "avancado"]):
        return 5
    if _window_has_marker(text, preferred, DESIRED_MARKERS + ["plus"], line_only=True):
        return 2
    return 4


# Re-export for callers that imported normalize from services.
# Implementation lives in job_understanding.


def _clean_skill_scores(
    result: dict[str, Any] | None,
    skills: list[dict[str, Any]],
    *,
    model: str = "v1",
) -> list[dict[str, Any]]:
    payload = _extract_skills_payload(result)
    if not payload:
        if model == "v2":
            return [
                {
                    "name": skill["name"],
                    "score": None if is_soft_skill(skill) else 0,
                    "confidence": 0.1,
                    "evidence_status": "needs_validation" if is_soft_skill(skill) else "not_found",
                    "evidence": [],
                }
                for skill in skills
            ]
        return [{"name": skill["name"], "score": 0, "evidence": "Sem avaliação da LLM."} for skill in skills]

    by_name: dict[str, dict[str, Any]] = {}
    for item in payload:
        name = str(item.get("name") or item.get("skill") or item.get("habilidade") or "").strip()
        if not name:
            continue
        by_name[normalize_text(name)] = item
        by_name[name.lower()] = item

    cleaned = []
    for skill in skills:
        expected = str(skill["name"])
        soft = is_soft_skill(skill)
        item = by_name.get(normalize_text(expected)) or by_name.get(expected.lower())
        if not item:
            expected_norm = normalize_text(expected)
            for key, value in by_name.items():
                key_norm = normalize_text(key)
                if expected_norm == key_norm or expected_norm in key_norm or key_norm in expected_norm:
                    item = value
                    break
        if not item:
            if model == "v2":
                cleaned.append(
                    {
                        "name": expected,
                        "score": None if soft else 0,
                        "confidence": 0.1,
                        "evidence_status": "needs_validation" if soft else "not_found",
                        "evidence": [],
                    }
                )
            else:
                cleaned.append({"name": expected, "score": 0, "evidence": "Sem avaliação da LLM."})
            continue

        raw_score = item.get("score", item.get("nota", item.get("rating")))
        score: int | None
        if raw_score is None or str(raw_score).strip().lower() in {"null", "none", ""}:
            score = None if (model == "v2" and soft) else 0
        else:
            try:
                score = max(0, min(5, int(float(raw_score))))
            except (TypeError, ValueError):
                score = None if (model == "v2" and soft) else 0

        evidence_list = normalize_evidence_list(
            item.get("evidence") or item.get("evidencia") or item.get("evidência")
        )
        status = normalize_evidence_status(
            item.get("evidence_status") or item.get("status"),
            score=score,
            is_soft=soft,
        )
        if model == "v2" and soft and (score is None or (score == 0 and status in {"not_found", "needs_validation"})):
            score = None
            status = "needs_validation"
            evidence_list = []

        confidence_raw = item.get("confidence", item.get("confianca"))
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw))) if confidence_raw is not None else None
        except (TypeError, ValueError):
            confidence = None
        if confidence is None:
            confidence = 0.8 if status == "explicit" else 0.35 if status == "inferred" else 0.15

        if model == "v2":
            cleaned.append(
                {
                    "name": expected,
                    "score": score,
                    "confidence": confidence,
                    "evidence_status": status,
                    "evidence": evidence_list,
                }
            )
        else:
            evidence = evidence_to_legacy_text(evidence_list, status)
            if not evidence_list and score and score > 0:
                evidence = "Evidência identificada no currículo pela LLM."
            elif not evidence_list:
                evidence = "Sem evidência textual no currículo."
            cleaned.append(
                {
                    "name": expected,
                    "score": 0 if score is None else score,
                    "evidence": evidence[:300],
                }
            )
    return cleaned
