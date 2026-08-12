from __future__ import annotations

import logging

import httpx

from app.compensation.domain.schemas import SearchResult
from app.compensation.logging_utils import log_event
from app.compensation.search.base import SearchEngine
from app.system_settings import get_system_value


class TavilySearchEngine(SearchEngine):
    name = "tavily"

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        api_key = get_system_value("TAVILY_API_KEY")
        if not api_key:
            log_event(
                "search_provider_skipped",
                level=logging.WARNING,
                provider=self.name,
                reason="missing_api_key",
                query=query,
            )
            return []
        base_url = get_system_value("TAVILY_BASE_URL", "https://api.tavily.com").rstrip("/")
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
        results = []
        for index, item in enumerate(response.json().get("results", []), start=1):
            url = str(item.get("url") or "")
            if not url:
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=url,
                    snippet=str(item.get("content") or ""),
                    provider=self.name,
                    rank=index,
                )
            )
        return results

    async def health(self) -> str:
        return "healthy" if get_system_value("TAVILY_API_KEY") else "missing_api_key"
