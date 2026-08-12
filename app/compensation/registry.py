from __future__ import annotations

from app.compensation.core import ProviderConfig, get_settings, provider_config
from app.compensation.crawlers.base import CompensationCrawler
from app.compensation.crawlers.catho import CathoCrawler
from app.compensation.crawlers.generic import GenericCrawler
from app.compensation.crawlers.glassdoor import GlassdoorCrawler
from app.compensation.crawlers.indeed import IndeedCrawler
from app.compensation.crawlers.vagas import VagasCrawler
from app.compensation.search.base import SearchEngine
from app.compensation.search.firecrawl import FirecrawlSearchEngine
from app.compensation.search.tavily import TavilySearchEngine


SEARCH_ENGINE_CLASSES: dict[str, type[SearchEngine]] = {
    "tavily": TavilySearchEngine,
    "firecrawl": FirecrawlSearchEngine,
}

CRAWLER_CLASSES: dict[str, type[CompensationCrawler]] = {
    "glassdoor": GlassdoorCrawler,
    "indeed": IndeedCrawler,
    "vagas": VagasCrawler,
    "catho": CathoCrawler,
    "generic": GenericCrawler,
}


class ProviderRegistry:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.search_config = {item.name: item for item in provider_config("search_engines")}
        self.crawler_config = {item.name: item for item in provider_config("crawlers")}

    def get_enabled_search_engines(self, override: list[str] | None = None) -> list[SearchEngine]:
        names = override if override is not None else self.settings.search_engines
        return self._instantiate_search_engines(names)

    def get_enabled_crawlers(self, override: list[str] | None = None) -> list[CompensationCrawler]:
        names = override if override is not None else self.settings.enabled_crawlers
        return self._instantiate_crawlers(names)

    def select_crawler(self, url: str, crawlers: list[CompensationCrawler]) -> CompensationCrawler:
        generic = None
        for crawler in crawlers:
            if crawler.name == "generic":
                generic = crawler
                continue
            if crawler.can_handle(url):
                return crawler
        return generic or GenericCrawler(self.crawler_config.get("generic", ProviderConfig("generic", True)))

    def _instantiate_search_engines(self, names: list[str]) -> list[SearchEngine]:
        providers = []
        for config in sorted(self.search_config.values(), key=lambda item: item.priority):
            if config.name not in names or not config.enabled:
                continue
            provider_class = SEARCH_ENGINE_CLASSES.get(config.name)
            if provider_class:
                providers.append(provider_class(config))
        return providers

    def _instantiate_crawlers(self, names: list[str]) -> list[CompensationCrawler]:
        providers = []
        for config in sorted(self.crawler_config.values(), key=lambda item: item.priority):
            if config.name not in names or not config.enabled:
                continue
            provider_class = CRAWLER_CLASSES.get(config.name)
            if provider_class:
                providers.append(provider_class(config))
        return providers
