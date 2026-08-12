from __future__ import annotations

from app.compensation.crawlers.base import CompensationCrawler


class CathoCrawler(CompensationCrawler):
    name = "catho"
    domains = ("catho.com.br",)

    def source_queries(self, profile: str, location: str) -> list[str]:
        return [
            f'site:catho.com.br "{profile}" salário {location}',
            f'site:catho.com.br "{profile}" remuneração {location}',
        ]
