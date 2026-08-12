from __future__ import annotations

from app.compensation.crawlers.base import CompensationCrawler


class VagasCrawler(CompensationCrawler):
    name = "vagas"
    domains = ("vagas.com.br",)

    def source_queries(self, profile: str, location: str) -> list[str]:
        return [
            f'site:vagas.com.br "{profile}" {location} salário',
            f'site:vagas.com.br "{profile}" PJ {location}',
        ]
