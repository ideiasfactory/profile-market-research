from __future__ import annotations

from collections import Counter

from app.compensation.core import load_yaml
from app.compensation.domain.schemas import CompensationObservation, ConfidenceSummary, Location
from app.compensation.utils import normalize_text


EVIDENCE_QUALITY = {
    "structured_data": 1.00,
    "page_content": 0.95,
    "salary_report": 0.95,
    "job_posting": 0.85,
    "search_snippet": 0.65,
}


def calculate_confidence(
    observations: list[CompensationObservation],
    expected_role: str,
    expected_location: Location,
) -> ConfidenceSummary:
    if not observations:
        return ConfidenceSummary(score=0.0, level="LOW")
    sample_score = min(1.0, len(observations) / 10)
    location_score = sum(location_match(obs.location, expected_location) for obs in observations) / len(observations)
    role_score = sum(role_match(obs.normalized_role or obs.role, expected_role) for obs in observations) / len(observations)
    source_score = average_source_quality(observations)
    freshness_score = 0.8
    evidence_score = sum(EVIDENCE_QUALITY.get(obs.evidence_type, 0.5) for obs in observations) / len(observations)
    score = round(
        sample_score * 0.25
        + location_score * 0.20
        + role_score * 0.20
        + source_score * 0.15
        + freshness_score * 0.10
        + evidence_score * 0.10,
        2,
    )
    level = "HIGH" if score >= 0.80 else "MEDIUM" if score >= 0.60 else "LOW"
    return ConfidenceSummary(score=score, level=level)


def location_match(observed: Location, expected: Location) -> float:
    if expected.city and normalize_text(observed.city) == normalize_text(expected.city):
        return 1.0
    if expected.state and normalize_text(observed.state) == normalize_text(expected.state):
        return 0.75
    if observed.country == expected.country:
        return 0.55
    return 0.3


def role_match(observed_role: str, expected_role: str) -> float:
    observed_words = set(normalize_text(observed_role).split())
    expected_words = set(normalize_text(expected_role).split())
    if not observed_words or not expected_words:
        return 0.5
    return min(1.0, len(observed_words & expected_words) / max(1, len(expected_words)))


def average_source_quality(observations: list[CompensationObservation]) -> float:
    registry = load_yaml("config/source_registry.yaml")
    values = []
    for observation in observations:
        values.append(float((registry.get(observation.source) or registry.get("unknown") or {}).get("quality_score", 0.5)))
    return sum(values) / len(values) if values else 0.0


def source_counts(observations: list[CompensationObservation]) -> Counter[str]:
    return Counter(obs.source for obs in observations)
