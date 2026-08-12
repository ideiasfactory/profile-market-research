from __future__ import annotations

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.compensation.core import get_settings
from app.compensation.domain.schemas import CompensationResearchRequest
from app.compensation.registry import ProviderRegistry
from app.compensation.services.history import list_cached_research, load_cached_research, load_latest_cached_research
from app.compensation.services.job_prefill import DEFAULT_PREFILL, map_job_to_compensation_prefill
from app.compensation.services.orchestrator import CompensationResearchOrchestrator
from app.storage import find_by_id, jobs_store
from app.system_settings import get_system_value
from app.tasks import task_store


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/health")
async def health():
    return {"status": "healthy"}


@router.get("/health/llm")
async def health_llm():
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
        return {"status": "healthy", "base_url": settings.ollama_base_url, "model": settings.ollama_model}
    except Exception as exc:
        return {"status": "unhealthy", "base_url": settings.ollama_base_url, "model": settings.ollama_model, "error": str(exc)}


@router.get("/health/providers")
async def health_providers():
    settings = get_settings()
    registry = ProviderRegistry()
    search = {engine.name: await engine.health() for engine in registry.get_enabled_search_engines()}
    crawlers = {crawler.name: "enabled" for crawler in registry.get_enabled_crawlers()}
    return {
        "search_engines": search,
        "crawlers": crawlers,
        "configured_search_engines": settings.search_engines,
        "api_keys": {
            "tavily": "set" if get_system_value("TAVILY_API_KEY") else "missing",
            "firecrawl": "set" if get_system_value("FIRECRAWL_API_KEY") else "missing",
        },
    }


@router.post("/api/v1/compensation/research")
async def research_compensation(payload: CompensationResearchRequest):
    return await CompensationResearchOrchestrator().research(payload)


@router.post("/api/v1/compensation/research/async")
async def research_compensation_async(payload: CompensationResearchRequest, background_tasks: BackgroundTasks):
    task = task_store.create("compensation_research")
    background_tasks.add_task(run_compensation_research_task, task.task_id, payload)
    return task.public()


async def run_compensation_research_task(task_id: str, payload: CompensationResearchRequest) -> None:
    def on_progress(percent: int, message: str) -> None:
        task_store.update(task_id, status="running", progress=percent, message=message)

    try:
        task_store.update(task_id, status="running", progress=1, message="Fila liberada. Iniciando pesquisa…")
        result = await CompensationResearchOrchestrator().research(payload, on_progress=on_progress)
        task_store.update(
            task_id,
            status="completed",
            progress=100,
            message="Pesquisa concluída.",
            result=result.model_dump(mode="json"),
            error=None,
        )
    except Exception as exc:
        task_store.update(
            task_id,
            status="failed",
            progress=100,
            message="Falha na pesquisa de remuneração.",
            error=str(exc),
        )


@router.get("/api/v1/compensation/history")
async def compensation_history():
    return {"items": list_cached_research()}


@router.get("/api/v1/compensation/history/{cache_key}")
async def compensation_history_item(cache_key: str):
    payload = load_cached_research(cache_key)
    if payload is None:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada no cache.")
    return payload


@router.get("/api/v1/compensation/prefill/{job_id}")
async def compensation_prefill_from_job(job_id: str):
    job = find_by_id(jobs_store.read(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vaga não encontrada.")
    return map_job_to_compensation_prefill(job)


@router.get("/compensation")
def compensation_page(request: Request):
    settings = get_settings()
    registry = ProviderRegistry()
    enabled_search = [engine.name for engine in registry.get_enabled_search_engines()]
    enabled_crawlers = [crawler.name for crawler in registry.get_enabled_crawlers()]
    history = list_cached_research()
    jobs = jobs_store.read()
    job_id = (request.query_params.get("job_id") or "").strip()
    selected_job = find_by_id(jobs, job_id) if job_id else None
    prefill = map_job_to_compensation_prefill(selected_job) if selected_job else dict(DEFAULT_PREFILL)
    if not selected_job and not prefill.get("profile"):
        prefill = {
            **DEFAULT_PREFILL,
            "profile": "Arquiteto de Soluções Senior Cloud e Microserviços",
            "skills": ["Azure", "AKS", "Kubernetes", "Microservices"],
            "location": {"city": "Campinas", "state": "SP", "country": "BR"},
        }
    selected_key = request.query_params.get("cache_key")
    if not selected_key and not selected_job and history:
        selected_key = history[0]["cache_key"]
    selected = load_cached_research(selected_key) if selected_key else None
    if not selected and not selected_job:
        selected = load_latest_cached_research()
    return templates.TemplateResponse(
        request,
        "compensation.html",
        {
            "title": "Compensation Intelligence",
            "search_engines": enabled_search,
            "crawlers": enabled_crawlers,
            "all_search_engines": ["tavily", "firecrawl"],
            "all_crawlers": ["glassdoor", "indeed", "vagas", "catho", "generic"],
            "api_keys": {
                "tavily": "set" if get_system_value("TAVILY_API_KEY") else "missing",
                "firecrawl": "set" if get_system_value("FIRECRAWL_API_KEY") else "missing",
            },
            "configured_search_engines": settings.search_engines,
            "history": history,
            "selected_cache_key": selected_key,
            "last_result": selected if not selected_job else None,
            "jobs": jobs,
            "selected_job": selected_job,
            "prefill": prefill,
        },
    )
