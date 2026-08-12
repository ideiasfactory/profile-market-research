from __future__ import annotations

import re
from typing import Iterable

from app.compensation.domain.schemas import (
    CompensationObservation,
    CompensationResearchRequest,
    Salary,
    SalaryPeriod,
)
from app.compensation.utils import normalize_text


SENIORITY_ALIASES: dict[str, set[str]] = {
    "intern": {"intern", "estagio", "estagiario", "trainee"},
    "junior": {"junior", "jr", "júnior", "entry", "entrylevel"},
    "pleno": {"pleno", "mid", "midlevel", "intermediario"},
    "senior": {"senior", "sr", "sênior"},
    "lead": {"lead", "techlead", "technicallead"},
    "principal": {"principal", "staff", "arquiteto principal"},
}

# Adjacent seniorities still useful for market banding.
SENIORITY_COMPATIBLE: dict[str, set[str]] = {
    "intern": {"intern"},
    "junior": {"junior", "intern"},
    "pleno": {"pleno"},
    "senior": {"senior", "lead", "principal"},
    "lead": {"lead", "senior", "principal"},
    "principal": {"principal", "lead", "senior"},
}

# Absolute plausibility for BR technology roles (before CLT→PJ conversion).
MIN_MONTHLY_BRL = 3_000.0
MAX_MONTHLY_BRL = 120_000.0
MIN_HOURLY_BRL = 40.0
MAX_HOURLY_BRL = 700.0
MIN_YEARLY_BRL = 36_000.0
MAX_YEARLY_BRL = 1_500_000.0
# Glassdoor/snippets often label monthly values as "anual".
YEARLY_MISLABEL_THRESHOLD = 60_000.0


def infer_seniority(*texts: str) -> str | None:
    from urllib.parse import unquote

    blob = normalize_text(" ".join(unquote(part) for part in texts if part))
    if not blob:
        return None
    # Prefer explicit tokens; check longer/higher keys first.
    ordered = (
        ("principal", SENIORITY_ALIASES["principal"]),
        ("lead", SENIORITY_ALIASES["lead"]),
        ("senior", SENIORITY_ALIASES["senior"]),
        ("pleno", SENIORITY_ALIASES["pleno"]),
        ("junior", SENIORITY_ALIASES["junior"]),
        ("intern", SENIORITY_ALIASES["intern"]),
    )
    for canonical, aliases in ordered:
        for alias in aliases:
            if re.search(rf"\b{re.escape(normalize_text(alias))}\b", blob):
                return canonical
    return None


def normalize_seniority_label(value: str | None) -> str | None:
    if not value:
        return None
    inferred = infer_seniority(value)
    if inferred:
        return inferred
    text = normalize_text(value)
    return text or None


def seniority_compatible(observed: str | None, requested: str | None) -> bool:
    requested_norm = normalize_seniority_label(requested)
    if not requested_norm:
        return True
    observed_norm = normalize_seniority_label(observed)
    if not observed_norm:
        # Unknown seniority: keep, but caller may lower confidence.
        return True
    allowed = SENIORITY_COMPATIBLE.get(requested_norm, {requested_norm})
    return observed_norm in allowed


def resolve_observation_seniority(observation: CompensationObservation, requested: str | None) -> str:
    # Prefer signals from the source page over request-stamped role labels.
    page_seniority = infer_seniority(observation.evidence, observation.source_url)
    if page_seniority:
        return page_seniority
    role_seniority = infer_seniority(observation.role, observation.normalized_role, observation.seniority)
    if role_seniority:
        return role_seniority
    return normalize_seniority_label(requested) or ""


def sanitize_salary_period(salary: Salary, evidence: str = "") -> Salary | None:
    """Fix common period mislabels and drop absurd values."""
    values = [value for value in [salary.average, salary.min, salary.max] if isinstance(value, (int, float)) and value > 0]
    if not values:
        return None
    average = float(salary.average) if salary.average is not None else sum(values) / len(values)
    period = salary.period
    text = normalize_text(evidence)

    # "R$ 4.120 anual" for tech roles in BR is almost always a mislabeled monthly.
    if period == SalaryPeriod.year and average < YEARLY_MISLABEL_THRESHOLD:
        if "mes" in text or "mensal" in text or "/mes" in text:
            period = SalaryPeriod.month
        elif "hora" in text or "/h" in text:
            period = SalaryPeriod.hour
        else:
            # Prefer month for mid-range values that look monthly (3k-60k).
            if average >= MIN_MONTHLY_BRL:
                period = SalaryPeriod.month
            else:
                return None

    if period == SalaryPeriod.year and not (MIN_YEARLY_BRL <= average <= MAX_YEARLY_BRL):
        return None
    if period == SalaryPeriod.month and not (MIN_MONTHLY_BRL <= average <= MAX_MONTHLY_BRL):
        return None
    if period == SalaryPeriod.hour and not (MIN_HOURLY_BRL <= average <= MAX_HOURLY_BRL):
        return None

    return salary.model_copy(update={"period": period})


def is_plausible_normalized(observation: CompensationObservation) -> bool:
    value = observation.normalized_salary.get("value")
    unit = observation.normalized_salary.get("period") or observation.normalized_salary.get("unit")
    monthly = observation.normalized_salary.get("monthly_equivalent")
    if not isinstance(value, (int, float)):
        return False
    if unit == "hour" and not (MIN_HOURLY_BRL <= float(value) <= MAX_HOURLY_BRL):
        return False
    if unit == "month" and not (MIN_MONTHLY_BRL <= float(value) <= MAX_MONTHLY_BRL):
        return False
    if isinstance(monthly, (int, float)) and not (MIN_MONTHLY_BRL <= float(monthly) <= MAX_MONTHLY_BRL * 1.6):
        # PJ monthly can exceed CLT max due to factor 1.5
        return False
    return True


def filter_observations(
    observations: Iterable[CompensationObservation],
    request: CompensationResearchRequest,
) -> tuple[list[CompensationObservation], list[str]]:
    """Drop seniority mismatches and implausible salaries before statistics."""
    kept: list[CompensationObservation] = []
    warnings: list[str] = []
    dropped_seniority = 0
    dropped_salary = 0

    for observation in observations:
        seniority = resolve_observation_seniority(observation, request.seniority)
        observation = observation.model_copy(update={"seniority": seniority})

        if not seniority_compatible(seniority, request.seniority):
            dropped_seniority += 1
            continue

        sanitized = sanitize_salary_period(observation.salary, observation.evidence)
        if sanitized is None:
            dropped_salary += 1
            continue
        observation = observation.model_copy(update={"salary": sanitized})
        kept.append(observation)

    if dropped_seniority:
        warnings.append(
            f"{dropped_seniority} observação(ões) removida(s) por senioridade incompatível com '{request.seniority}'."
        )
    if dropped_salary:
        warnings.append(
            f"{dropped_salary} observação(ões) removida(s) por valor/período salarial implausível."
        )
    return kept, warnings


def exclude_implausible_normalized(
    observations: list[CompensationObservation],
) -> tuple[list[CompensationObservation], int]:
    result: list[CompensationObservation] = []
    excluded = 0
    for observation in observations:
        if is_plausible_normalized(observation):
            result.append(observation)
        else:
            excluded += 1
            result.append(observation.model_copy(update={"excluded_from_statistics": True}))
    return result, excluded
