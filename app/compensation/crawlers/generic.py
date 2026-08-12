from __future__ import annotations

from app.compensation.crawlers.base import CompensationCrawler


class GenericCrawler(CompensationCrawler):
    name = "generic"
    domains = ()

    def can_handle(self, url: str) -> bool:
        return True

    def source_queries(self, profile: str, location: str) -> list[str]:
        return [
            f'"{profile}" salário {location}',
            f'"{profile}" remuneração tecnologia {location}',
            f'pesquisa salarial "{profile}" tecnologia Brasil',
        ]
