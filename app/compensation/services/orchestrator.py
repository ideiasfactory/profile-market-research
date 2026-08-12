from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.compensation.core import DATA_DIR, append_jsonl, get_settings
from app.compensation.domain.schemas import (
    CompensationObservation,
    CompensationResearchRequest,
    CompensationResearchResponse,
    ProviderSummary,
    SampleSummary,
    SourceSummary,
)
from app.compensation.llm.extractor import extract_observations
from app.compensation.llm.ollama_client import compensation_llm
from app.compensation.logging_utils import bind_research_id, log_event, reset_research_id
from app.compensation.registry import ProviderRegistry
from app.compensation.services.confidence import calculate_confidence
from app.compensation.services.deduplication import deduplicate_observations, deduplicate_search_results
from app.compensation.services.normalization import normalize_observations
from app.compensation.services.profile_normalizer import normalize_profile
from app.compensation.services.quality import exclude_implausible_normalized, filter_observations
from app.compensation.services.query_planner import generate_queries
from app.compensation.services.statistics import calculate_market_stats
from app.compensation.utils import now_iso, stable_id


ProgressCallback = Callable[[int, str], None]


class CompensationResearchOrchestrator:
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()
        self.settings = get_settings()
        self.llm = compensation_llm()

    async def research(
        self,
        request: CompensationResearchRequest,
        on_progress: ProgressCallback | None = None,
    ) -> CompensationResearchResponse:
        def progress(percent: int, message: str) -> None:
            capped = max(0, min(100, int(percent)))
            if on_progress:
                on_progress(capped, message)
            log_event("research_progress", progress=capped, message=message)

        progress(3, "Verificando cache da consulta…")
        cached = None if request.force_refresh else self._read_cache(request)
        if cached:
            log_event(
                "research_cache_hit",
                research_id=cached.research_id,
                profile=request.profile,
                sample_observations=cached.sample.observations,
            )
            progress(100, "Resultado encontrado no cache.")
            return cached

        research_id = stable_id("research", datetime.now(timezone.utc).isoformat(), request.model_dump_json())
        token = bind_research_id(research_id)
        started = time.perf_counter()
        warnings: list[str] = []
        try:
            provider_override = request.providers
            search_engines = self.registry.get_enabled_search_engines(
                provider_override.search_engines if provider_override else None
            )
            crawlers = self.registry.get_enabled_crawlers(provider_override.crawlers if provider_override else None)
            requested_search = (
                provider_override.search_engines
                if provider_override and provider_override.search_engines is not None
                else self.settings.search_engines
            )
            requested_crawlers = (
                provider_override.crawlers
                if provider_override and provider_override.crawlers is not None
                else self.settings.enabled_crawlers
            )

            log_event(
                "research_started",
                profile=request.profile,
                seniority=request.seniority,
                location=request.location.model_dump(),
                target_contract=request.target_contract.value,
                force_refresh=request.force_refresh,
                source_job_id=request.source_job_id,
                requested_search_engines=requested_search,
                requested_crawlers=requested_crawlers,
                enabled_search_engines=[engine.name for engine in search_engines],
                enabled_crawlers=[crawler.name for crawler in crawlers],
            )

            if not search_engines:
                warning = (
                    "Nenhum search engine habilitado (search_engines vazio ou sem API key). "
                    "Sem URLs descobertas, os crawlers não são executados e a amostra fica zerada."
                )
                warnings.append(warning)
                log_event("research_no_search_engines", level=logging.WARNING, detail=warning)

            progress(10, "Normalizando perfil com LLM…")
            profile = await normalize_profile(request, self.llm)
            log_event(
                "profile_normalized",
                normalized_role=profile.normalized_role,
                role_family=profile.role_family,
                seniority=profile.seniority,
                skills=profile.skills,
            )

            progress(18, "Planejando queries de busca…")
            queries = generate_queries(request, profile, crawlers)
            log_event("queries_planned", count=len(queries), queries=queries)

            progress(25, f"Buscando fontes ({len(search_engines)} search engine(s), {len(queries)} queries)…")
            search_results = await self._parallel_search(queries, search_engines)
            search_results = deduplicate_search_results(search_results)
            log_event(
                "search_completed",
                results=len(search_results),
                by_provider=dict(Counter(item.provider for item in search_results)),
                urls=[item.url for item in search_results[:10]],
            )
            progress(40, f"Search concluído: {len(search_results)} URL(s) encontradas.")

            if search_engines and not search_results:
                warning = (
                    "Search engines executaram, mas não retornaram URLs. "
                    "Verifique API keys, cotas e as queries geradas."
                )
                warnings.append(warning)
                log_event("research_empty_search_results", level=logging.WARNING, detail=warning)

            if not search_results and crawlers:
                warning = (
                    f"Crawlers configurados ({', '.join(crawler.name for crawler in crawlers)}) "
                    "não foram usados porque não há URLs de entrada."
                )
                warnings.append(warning)
                log_event(
                    "research_crawlers_skipped",
                    level=logging.WARNING,
                    crawlers=[crawler.name for crawler in crawlers],
                )

            crawl_targets = search_results[:25]
            progress(45, f"Crawleando {len(crawl_targets)} página(s)…")
            documents = await self._crawl_results(
                crawl_targets,
                crawlers,
                on_progress=lambda done, total: progress(
                    45 + int((done / max(total, 1)) * 20),
                    f"Crawling {done}/{total} páginas…",
                ),
            )
            crawl_status = dict(Counter(document.status for document in documents))
            crawl_methods = dict(Counter(document.crawl_method for document in documents))
            log_event(
                "crawl_completed",
                documents=len(documents),
                status=crawl_status,
                methods=crawl_methods,
                sources=sorted({document.source for document in documents}),
            )
            progress(66, f"Crawl concluído: {len(documents)} documento(s).")

            observations: list[CompensationObservation] = []
            total_docs = max(len(documents), 1)
            for index, document in enumerate(documents, start=1):
                progress(
                    66 + int((index / total_docs) * 20),
                    f"Extraindo salários {index}/{len(documents)} ({document.source})…",
                )
                extracted = await extract_observations(document, request, profile.normalized_role, self.llm)
                if extracted:
                    log_event(
                        "observations_extracted",
                        source=document.source,
                        url=document.url,
                        count=len(extracted),
                        crawl_method=document.crawl_method,
                        status=document.status,
                    )
                observations.extend(extracted)

            progress(88, "Filtrando senioridade e qualidade salarial…")
            observations = deduplicate_observations(observations)
            observations, quality_warnings = filter_observations(observations, request)
            warnings.extend(quality_warnings)
            log_event(
                "observations_filtered",
                kept=len(observations),
                quality_warnings=quality_warnings,
            )
            progress(92, "Normalizando remuneração e calculando estatísticas…")
            observations = normalize_observations(observations, request.target_contract)
            observations, implausible = exclude_implausible_normalized(observations)
            if implausible:
                warning = (
                    f"{implausible} observação(ões) excluída(s) das estatísticas "
                    "por faixa salarial irreal após normalização."
                )
                warnings.append(warning)
                log_event("observations_implausible_excluded", count=implausible, level=logging.WARNING)
            market, observations, stats_warnings = calculate_market_stats(observations, request.target_contract)
            warnings.extend(stats_warnings)
            confidence = calculate_confidence(
                [obs for obs in observations if not obs.excluded_from_statistics],
                profile.normalized_role,
                request.location,
            )
            if confidence.level == "LOW":
                warnings.append("Confidence LOW; aumente fontes, localidade ou amostra antes de decisão comercial.")

            progress(97, "Persistindo resultado…")
            response = CompensationResearchResponse(
                research_id=research_id,
                profile=profile,
                market=market,
                sample=SampleSummary(
                    observations=len([obs for obs in observations if not obs.excluded_from_statistics]),
                    sources=len({obs.source_url for obs in observations if not obs.excluded_from_statistics}),
                ),
                providers=ProviderSummary(
                    search_engines_used=[engine.name for engine in search_engines],
                    crawlers_used=sorted(
                        {document.source for document in documents if document.status in {"success", "partial"}}
                    ),
                ),
                confidence=confidence,
                sources=self._summarize_sources(observations),
                warnings=dedupe_strings(warnings),
                observations=observations,
                created_at=datetime.now(timezone.utc),
            )
            self._persist(request, response)
            log_event(
                "research_completed",
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                sample_observations=response.sample.observations,
                sample_sources=response.sample.sources,
                confidence=response.confidence.level,
                confidence_score=response.confidence.score,
                warnings=response.warnings,
                search_engines_used=response.providers.search_engines_used,
                crawlers_used=response.providers.crawlers_used,
            )
            progress(100, "Pesquisa concluída.")
            return response
        except Exception:
            log_event(
                "research_failed",
                level=logging.ERROR,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                profile=request.profile,
            )
            raise
        finally:
            reset_research_id(token)

    async def _parallel_search(self, queries: list[str], search_engines: list[Any]) -> list[Any]:
        if not search_engines:
            return []
        semaphore = asyncio.Semaphore(self.settings.max_parallel_searches)

        async def run(engine: Any, query: str) -> list[Any]:
            async with semaphore:
                try:
                    results = await engine.search(query, engine.config.max_results)
                    log_event(
                        "search_query_completed",
                        provider=engine.name,
                        query=query,
                        results=len(results),
                    )
                    return results
                except Exception as exc:
                    log_event(
                        "search_query_failed",
                        level=logging.WARNING,
                        provider=engine.name,
                        query=query,
                        error=str(exc),
                    )
                    return []

        tasks = [run(engine, query) for engine in search_engines for query in queries]
        results = await asyncio.gather(*tasks)
        merged = [item for group in results for item in group]
        return sorted(merged, key=lambda item: (item.rank, item.provider))

    async def _crawl_results(
        self,
        search_results: list[Any],
        crawlers: list[Any],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[Any]:
        if not search_results:
            return []
        semaphore = asyncio.Semaphore(self.settings.max_parallel_crawls)
        total = len(search_results)
        done = 0
        done_lock = asyncio.Lock()

        async def run(result: Any) -> Any:
            nonlocal done
            crawler = self.registry.select_crawler(result.url, crawlers)
            async with semaphore:
                started = time.perf_counter()
                document = await crawler.crawl(result.url, result)
                log_event(
                    "crawl_document_completed",
                    crawler=crawler.name,
                    url=result.url,
                    status=document.status,
                    method=document.crawl_method,
                    content_chars=len(document.content or ""),
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                )
                async with done_lock:
                    done += 1
                    if on_progress:
                        on_progress(done, total)
                return document

        return await asyncio.gather(*(run(result) for result in search_results))

    def _summarize_sources(self, observations: list[CompensationObservation]) -> list[SourceSummary]:
        by_url: dict[str, list[CompensationObservation]] = defaultdict(list)
        for observation in observations:
            if not observation.excluded_from_statistics:
                by_url[observation.source_url].append(observation)
        summaries = []
        for url, items in by_url.items():
            summaries.append(
                SourceSummary(
                    name=items[0].source,
                    url=url,
                    observations=len(items),
                    retrieved_at=items[0].retrieved_at,
                )
            )
        return summaries

    def _cache_key(self, request: CompensationResearchRequest) -> str:
        providers = request.providers.model_dump() if request.providers else {}
        payload = {
            "profile": request.profile,
            "skills": sorted(request.skills),
            "seniority": request.seniority,
            "allocation_model": request.allocation_model,
            "location": request.location.model_dump(),
            "target_contract": request.target_contract,
            "providers": providers,
        }
        return stable_id(json.dumps(payload, sort_keys=True, default=str), length=32)

    def _cache_path(self, request: CompensationResearchRequest) -> Path:
        return DATA_DIR / "compensation_cache" / f"{self._cache_key(request)}.json"

    def _read_cache(self, request: CompensationResearchRequest) -> CompensationResearchResponse | None:
        path = self._cache_path(request)
        if not path.exists():
            return None
        age_seconds = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        if age_seconds > self.settings.cache_ttl_days * 86400:
            return None
        with path.open("r", encoding="utf-8") as file:
            return CompensationResearchResponse.model_validate(json.load(file))

    def _persist(self, request: CompensationResearchRequest, response: CompensationResearchResponse) -> None:
        payload = response.model_dump(mode="json")
        cache_path = self._cache_path(request)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        append_jsonl(DATA_DIR / "research_history.jsonl", payload)
        for observation in response.observations:
            append_jsonl(DATA_DIR / "observations.jsonl", observation.model_dump(mode="json"))
        log_event(
            "research_persisted",
            cache_path=str(cache_path),
            observations_persisted=len(response.observations),
            persisted_at=now_iso(),
        )


def dedupe_strings(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
