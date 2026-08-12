from __future__ import annotations

import logging

import httpx

from app.compensation.domain.schemas import SearchResult
from app.compensation.logging_utils import log_event
from app.compensation.search.base import SearchEngine
from app.system_settings import get_system_value


class FirecrawlSearchEngine(SearchEngine):
    name = "firecrawl"

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        api_key = get_system_value("FIRECRAWL_API_KEY")
        if not api_key:
            log_event(
                "search_provider_skipped",
                level=logging.WARNING,
                provider=self.name,
                reason="missing_api_key",
                query=query,
            )
            return []
        base_url = get_system_value("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev").rstrip("/")
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/v1/search",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"query": query, "limit": max_results},
            )
            response.raise_for_status()
        raw_results = response.json().get("data") or response.json().get("results") or []
        results = []
        for index, item in enumerate(raw_results, start=1):
            url = str(item.get("url") or "")
            if not url:
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=url,
                    snippet=str(item.get("description") or item.get("snippet") or item.get("markdown") or ""),
                    provider=self.name,
                    rank=index,
                )
            )
        return results

    async def health(self) -> str:
        return "healthy" if get_system_value("FIRECRAWL_API_KEY") else "missing_api_key"
