from __future__ import annotations

from app.compensation.crawlers.base import CompensationCrawler
from app.compensation.domain.schemas import CompensationResearchRequest, NormalizedProfile


def generate_queries(
    request: CompensationResearchRequest,
    profile: NormalizedProfile,
    crawlers: list[CompensationCrawler],
) -> list[str]:
    location = " ".join(part for part in [request.location.city, request.location.state] if part).strip() or "Brasil"
    skills = " ".join(request.skills[:4])
    base_role = profile.normalized_role or request.profile
    queries = [
        f'"{request.profile}" salário {location}',
        f'"{base_role}" salário {location}',
        f'"{base_role}" remuneração {location}',
        f'"{base_role}" {skills} salário tecnologia Brasil',
        f'"{base_role}" salary {location}',
    ]
    for crawler in crawlers:
        if crawler.name != "generic":
            queries.extend(crawler.source_queries(base_role, location))
    deduped = []
    seen = set()
    for query in queries:
        normalized = " ".join(query.split()).lower()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(query)
    return deduped[:10]
