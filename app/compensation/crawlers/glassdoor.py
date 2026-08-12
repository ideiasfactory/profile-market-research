from __future__ import annotations

from app.compensation.crawlers.base import CompensationCrawler


class GlassdoorCrawler(CompensationCrawler):
    name = "glassdoor"
    domains = ("glassdoor.com.br",)

    def source_queries(self, profile: str, location: str) -> list[str]:
        return [
            f'site:glassdoor.com.br "{profile}" salário {location}',
            f'site:glassdoor.com.br "{profile}" salarios {location}',
            f'site:glassdoor.com.br "Cloud Solution Architect" salário {location}',
        ]
