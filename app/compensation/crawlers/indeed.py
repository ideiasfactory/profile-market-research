from __future__ import annotations

from app.compensation.crawlers.base import CompensationCrawler


class IndeedCrawler(CompensationCrawler):
    name = "indeed"
    domains = ("br.indeed.com",)

    def source_queries(self, profile: str, location: str) -> list[str]:
        return [
            f'site:br.indeed.com/career "{profile}" {location} salário',
            f'site:br.indeed.com "{profile}" salário {location}',
        ]
