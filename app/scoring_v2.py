from __future__ import annotations

from typing import Any

from app.scoring_config import (
    AUTO_ELIMINATE_ON_CRITICAL_GAP,
    DIMENSION_WEIGHTS,
    MUST_HAVE_COVERED_MIN_SCORE,
    VERDICT_THRESHOLDS,
    normalize_dimension_weights,
)


def skill_score_to_pct(score: float | int | None) -> float | None:
    if score is None:
        return None
    return round(max(0.0, min(5.0, float(score))) / 5.0 * 100.0, 2)


def weighted_dimension_pct(items: list[dict[str, Any]]) -> float | None:
    """
    Compute 0–100 dimension from scored items.
    Items with score=None are excluded from the denominator (soft skills without evidence).
    """
    weighted_points = 0.0
    max_points = 0.0
    for item in items:
        score = item.get("score")
        if score is None:
            continue
        weight = float(item.get("weight") or 1)
        if weight <= 0:
            continue
        clamped = max(0.0, min(5.0, float(score)))
        weighted_points += clamped * weight
        max_points += 5.0 * weight
    if max_points <= 0:
        return None
    return round((weighted_points / max_points) * 100.0, 2)


def compute_must_have_coverage(
    items: list[dict[str, Any]],
    *,
    min_score: int = MUST_HAVE_COVERED_MIN_SCORE,
) -> dict[str, Any]:
    must = [item for item in items if str(item.get("tier") or "").upper() == "MUST_HAVE"]
    total = len(must)
    covered_names: list[str] = []
    missing_names: list[str] = []
    for item in must:
        score = item.get("score")
        name = str(item.get("name") or "")
        if score is not None and float(score) >= min_score:
            covered_names.append(name)
        else:
            missing_names.append(name)
    covered = len(covered_names)
    ratio = round(covered / total, 4) if total else 1.0
    return {
        "covered": covered,
        "total": total,
        "ratio": ratio,
        "covered_skills": covered_names,
        "missing_skills": missing_names,
        "min_score": min_score,
    }


def classify_critical_gaps(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Classify missing/weak skills:
    - critical: must-have missing or score 0 / not_found / negative
    - important: core missing/weak
    - minor: supporting missing
    - documentation_gap: soft/other with needs_validation or inferred-only weak evidence
    """
    gaps: list[dict[str, Any]] = []
    for item in items:
        tier = str(item.get("tier") or "").upper()
        score = item.get("score")
        status = str(item.get("evidence_status") or "")
        name = str(item.get("name") or "")
        if not name:
            continue

        if status == "needs_validation" or (score is None and tier == "SOFT"):
            gaps.append(
                {
                    "name": name,
                    "severity": "documentation_gap",
                    "tier": tier,
                    "score": score,
                    "evidence_status": status,
                    "reason": "Sem evidência textual suficiente; validar em entrevista.",
                }
            )
            continue

        weak = score is None or float(score) <= 1 or status in {"not_found", "negative"}
        if not weak:
            continue

        if tier == "MUST_HAVE":
            severity = "critical"
        elif tier == "CORE":
            severity = "important"
        elif tier in {"SUPPORTING", "DIFFERENTIAL"}:
            severity = "minor"
        else:
            severity = "documentation_gap"

        gaps.append(
            {
                "name": name,
                "severity": severity,
                "tier": tier,
                "score": score,
                "evidence_status": status,
                "reason": _gap_reason(tier, status, score),
            }
        )
    return gaps


def _gap_reason(tier: str, status: str, score: Any) -> str:
    if status == "negative":
        return "Evidência negativa ou contraditória no currículo."
    if status == "not_found" or score == 0:
        return f"Sem evidência para requisito {tier or 'técnico'}."
    return "Evidência fraca frente ao requisito."


def compute_group_scores(
    items: list[dict[str, Any]],
    skill_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_name = {str(item.get("name") or "").lower(): item for item in items}
    results: list[dict[str, Any]] = []
    for group in skill_groups or []:
        group_name = str(group.get("name") or "").strip()
        if not group_name:
            continue
        members = []
        for skill_name in group.get("skills") or []:
            item = by_name.get(str(skill_name).lower())
            if item:
                members.append(item)
        # Also include items tagged with this group.
        for item in items:
            if str(item.get("group") or "").lower() == group_name.lower() and item not in members:
                members.append(item)
        pct = weighted_dimension_pct(members)
        covered = sum(1 for m in members if m.get("score") is not None and float(m["score"]) >= 3)
        results.append(
            {
                "name": group_name,
                "score": pct,
                "skills_total": len(members),
                "skills_covered": covered,
                "coverage_ratio": round(covered / len(members), 4) if members else None,
            }
        )
    return results


def compute_score_breakdown(
    items: list[dict[str, Any]],
    *,
    role_fit: float | None,
    context_fit: float | None,
    dimension_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    must_core = [
        item
        for item in items
        if str(item.get("tier") or "").upper() in {"MUST_HAVE", "CORE"}
        and str(item.get("category") or "") != "Soft skill"
    ]
    supporting = [item for item in items if str(item.get("tier") or "").upper() == "SUPPORTING"]
    # Core technical includes must+core; supporting folded at reduced influence via its own weight in items.
    technical_pool = must_core + supporting
    soft = [item for item in items if str(item.get("tier") or "").upper() == "SOFT"]
    differentials = [item for item in items if str(item.get("tier") or "").upper() == "DIFFERENTIAL"]

    core_technical = weighted_dimension_pct(technical_pool)
    behavioral = weighted_dimension_pct(soft)
    differentials_pct = weighted_dimension_pct(differentials)

    # Neutral fill when a dimension has no evaluable items.
    role = _clamp_pct(role_fit)
    context = _clamp_pct(context_fit)
    dims = {
        "core_technical_fit": core_technical if core_technical is not None else 0.0,
        "role_fit": role if role is not None else 50.0,
        "context_fit": context if context is not None else 50.0,
        "behavioral_fit": behavioral if behavioral is not None else 50.0,
        "differentials": differentials_pct if differentials_pct is not None else 0.0,
    }

    weights = normalize_dimension_weights(dimension_weights or DIMENSION_WEIGHTS)
    # If differentials have no items, redistribute weight.
    active_weights = dict(weights)
    if differentials_pct is None:
        freed = active_weights.pop("differentials", 0.0)
        if freed and active_weights:
            boost = freed / len(active_weights)
            active_weights = {k: v + boost for k, v in active_weights.items()}
    if behavioral is None:
        freed = active_weights.pop("behavioral_fit", 0.0)
        if freed and active_weights:
            boost = freed / len(active_weights)
            active_weights = {k: v + boost for k, v in active_weights.items()}

    active_weights = normalize_dimension_weights(active_weights)
    final = round(sum(dims[key] * active_weights.get(key, 0.0) for key in dims), 2)

    return {
        "dimensions": {key: round(value, 2) for key, value in dims.items()},
        "weights": active_weights,
        "final_score": final,
        "core_technical_fit": round(dims["core_technical_fit"], 2),
        "role_fit": round(dims["role_fit"], 2),
        "context_fit": round(dims["context_fit"], 2),
        "behavioral_fit": round(dims["behavioral_fit"], 2),
        "differentials": round(dims["differentials"], 2),
    }


def decide_verdict(
    *,
    final_score: float,
    must_have_coverage: dict[str, Any],
    critical_gaps: list[dict[str, Any]],
    role_fit: float | None = None,
    thresholds: dict[str, float] | None = None,
    auto_eliminate: bool | None = None,
) -> str:
    """
    Verdict labels (v2): strong_fit | recommended | evaluate | not_recommended
    """
    th = thresholds or VERDICT_THRESHOLDS
    eliminate = AUTO_ELIMINATE_ON_CRITICAL_GAP if auto_eliminate is None else auto_eliminate

    has_critical = any(g.get("severity") == "critical" for g in critical_gaps)
    coverage_ratio = float(must_have_coverage.get("ratio") or 0.0)
    role = _clamp_pct(role_fit)

    if eliminate and has_critical:
        return "not_recommended"

    # Missing most must-haves → not recommended unless role/context salvage is strong (evaluate).
    if must_have_coverage.get("total", 0) > 0 and coverage_ratio == 0:
        if role is not None and role >= 70 and final_score >= th["evaluate"]:
            return "evaluate"
        return "not_recommended"

    if final_score >= th["strong_fit"] and coverage_ratio >= 0.75 and not has_critical:
        return "strong_fit"
    if final_score >= th["recommended"] and coverage_ratio >= 0.5:
        if has_critical:
            return "evaluate"
        return "recommended"
    if final_score >= th["evaluate"] or (has_critical and final_score >= th["evaluate"] - 10):
        return "evaluate"
    return "not_recommended"


def build_v2_score_result(
    *,
    job: dict[str, Any],
    candidate: dict[str, Any],
    items: list[dict[str, Any]],
    method: str,
    role_fit: float | None,
    context_fit: float | None,
    skill_groups: list[dict[str, Any]] | None = None,
    strengths: list[str] | None = None,
    interview_validation: list[str] | None = None,
    narrative: dict[str, str] | None = None,
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coverage = compute_must_have_coverage(items)
    gaps = classify_critical_gaps(items)
    breakdown = compute_score_breakdown(items, role_fit=role_fit, context_fit=context_fit)
    group_scores = compute_group_scores(items, skill_groups or [])
    verdict_label = decide_verdict(
        final_score=breakdown["final_score"],
        must_have_coverage=coverage,
        critical_gaps=gaps,
        role_fit=role_fit,
    )

    strength_names = strengths or [
        str(item["name"])
        for item in items
        if item.get("score") is not None and float(item["score"]) >= 4
    ][:8]

    gap_names = [
        g["name"] for g in gaps if g.get("severity") in {"critical", "important"}
    ][:8]

    narrative = narrative or {}
    return {
        "job_id": job["id"],
        "candidate_id": candidate["id"],
        "job_title": job.get("title", ""),
        "candidate_name": candidate.get("name", ""),
        "final_score": breakdown["final_score"],
        "method": method,
        "scoring_model_version": "v2",
        "items": items,
        "score_breakdown": breakdown,
        "must_have_coverage": coverage,
        "critical_gaps": gaps,
        "group_scores": group_scores,
        "role_fit": breakdown["role_fit"],
        "context_fit": breakdown["context_fit"],
        "strengths": strength_names,
        "gaps": gap_names,
        "interview_validation": interview_validation or [],
        "profile_summary": narrative.get("profile_summary", ""),
        "verdict": narrative.get("verdict", ""),
        "verdict_label": verdict_label,
        "audit": audit or {},
    }


def _clamp_pct(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def verdict_label_v1_from_score(final_score: float) -> str:
    if final_score >= 75:
        return "recomendado"
    if final_score >= 50:
        return "considerar"
    return "nao_recomendado"
