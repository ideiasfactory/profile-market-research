from __future__ import annotations

from abc import ABC, abstractmethod

from app.compensation.core import ProviderConfig
from app.compensation.domain.schemas import SearchResult


class SearchEngine(ABC):
    name: str

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        raise NotImplementedError

    async def health(self) -> str:
        return "configured"
