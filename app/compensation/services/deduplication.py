from __future__ import annotations

from app.compensation.domain.schemas import CompensationObservation, SearchResult
from app.compensation.utils import canonicalize_url, stable_id


def deduplicate_search_results(results: list[SearchResult]) -> list[SearchResult]:
    seen = set()
    deduped = []
    for result in results:
        url = canonicalize_url(result.url)
        if url in seen:
            continue
        seen.add(url)
        deduped.append(result.model_copy(update={"url": url}))
    return deduped


def deduplicate_observations(observations: list[CompensationObservation]) -> list[CompensationObservation]:
    seen = set()
    deduped = []
    for observation in observations:
        salary = observation.normalized_salary or observation.observed_salary or observation.salary.model_dump()
        key = stable_id(observation.normalized_role, observation.source_url, salary, observation.location.model_dump())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(observation.model_copy(update={"id": observation.id or key}))
    return deduped
