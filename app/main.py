from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import markdown as markdown_lib
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.compensation import router as compensation_router
from app.business_settings import (
    VALUE_TYPES,
    delete_business_parameter,
    format_business_context,
    get_business_settings,
    save_business_settings,
    upsert_business_parameter,
)
from app.env_loader import load_app_env
from app.external_api_usage import fetch_all_external_api_usage
from app.gpt import router as gpt_router
from app.llm import LocalLLM, OpenAILLM, active_llm_provider, get_llm
from app.llm_usage import summarize_usage
from app.logging_config import configure_logging
from app.resume_ingest import resolve_resume_content
from app.scoring_config import SCORING_MODEL, active_scoring_model
from app.services import analyse_job, build_score_chart_data, extract_candidate, normalize_job_analysis, score_candidate
from app.storage import candidates_store, domains_store, find_by_id, jobs_store, new_id, scores_store, upsert
from app.prompt_store import (
    get_managed_prompt,
    get_prompt_version_content,
    grouped_managed_prompts,
    list_managed_prompts,
    revert_prompt_version,
    save_prompt_edit,
)
from app.system_settings import (
    apply_system_settings_to_environ,
    get_system_settings,
    save_system_settings,
)
from app.tasks import task_store


load_app_env()
apply_system_settings_to_environ()
configure_logging()

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_GPT_SLIM_PATH = REPO_ROOT / "llm-tools" / "tool-openwebui" / "openapi.slim.3.0.json"
OPENAPI_GPT_SLIM_STATIC = Path(__file__).resolve().parent / "static" / "openapi-gpt-slim.json"

app = FastAPI(title="Professional Profile Analyser")

# Open WebUI User Tool Servers fetch OpenAPI + call APIs from the browser (CORS required).
# Global Tool Servers call from the Open WebUI container (no CORS needed).
_cors_raw = (os.getenv("CORS_ALLOW_ORIGINS") or "http://127.0.0.1:3000,http://localhost:3000").strip()
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(compensation_router)
app.include_router(gpt_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["markdown"] = lambda value: markdown_lib.markdown(
    value or "",
    extensions=["extra", "sane_lists", "nl2br"],
)
templates.env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)


def _llm_status() -> dict[str, Any]:
    local = LocalLLM()
    openai = OpenAILLM()
    return {
        "llm_provider_default": active_llm_provider(),
        "llm_configured": local.configured,
        "openai_configured": openai.configured,
        "openai_model": openai.model,
        "local_model": local.model,
    }


@app.get("/openapi-gpt-slim.json", include_in_schema=False)
def openapi_gpt_slim() -> FileResponse:
    """Slim OpenAPI 3.0 for Open WebUI tool servers (URL import).

    Prefer this over FastAPI's full `/openapi.json`, which includes HTML UI routes.
    Open WebUI default path field is `openapi.json`; set Path to `openapi-gpt-slim.json`.
    """
    path = OPENAPI_GPT_SLIM_PATH if OPENAPI_GPT_SLIM_PATH.is_file() else OPENAPI_GPT_SLIM_STATIC
    if not path.is_file():
        raise HTTPException(status_code=404, detail="openapi-gpt-slim.json not found")
    return FileResponse(path, media_type="application/json", filename="openapi-gpt-slim.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _progress(task_id: str, progress: int, message: str, status: str = "running") -> None:
    task_store.update(task_id, progress=progress, message=message, status=status)


async def run_analyse_job_task(task_id: str, fields: dict[str, Any]) -> None:
    try:
        _progress(task_id, 10, "Validando dados da vaga")
        jobs = jobs_store.read()
        item_id = str(fields.get("item_id") or "")
        existing = find_by_id(jobs, item_id) if item_id else None
        save_mode = str(fields.get("save_mode") or "reanalyse").strip().lower()
        provider = active_llm_provider(str(fields.get("llm_provider") or "") or None)
        llm = get_llm(provider)
        payload = {
            "id": item_id or new_id(),
            "title": str(fields["title"]).strip(),
            "description": str(fields["description"]).strip(),
            "profile": str(fields["profile"]).strip(),
            "seniority": str(fields["seniority"]).strip(),
            "job_description": str(fields["job_description"]).strip(),
            "ideal_candidate_context": str(fields.get("ideal_candidate_context") or "").strip(),
            "compensation_type": fields["compensation_type"],
            "compensation_min": float(fields["compensation_min"]),
            "compensation_max": float(fields["compensation_max"]),
            "work_location": fields["work_location"],
            "created_at": existing.get("created_at") if existing else now_iso(),
            "updated_at": now_iso(),
        }

        if save_mode == "save":
            _progress(task_id, 40, "Salvando critérios editados")
            manual = fields.get("analysis")
            if isinstance(manual, dict):
                payload["analysis"] = normalize_job_analysis(manual)
            elif existing and existing.get("analysis"):
                payload["analysis"] = normalize_job_analysis(existing.get("analysis"))
            else:
                payload["analysis"] = normalize_job_analysis({})
            message = "Vaga e critérios salvos com sucesso"
        else:
            _progress(task_id, 35, f"Analisando vaga com LLM ({provider})")
            payload["analysis"] = await analyse_job(payload, llm)
            message = "Vaga analisada com sucesso"

        _progress(task_id, 85, "Persistindo vaga")
        upsert(jobs, payload)
        jobs_store.write(jobs)

        task_store.update(
            task_id,
            status="completed",
            progress=100,
            message=message,
            redirect_url=f"/jobs/{payload['id']}",
        )
    except Exception as exc:
        task_store.update(
            task_id,
            status="failed",
            progress=100,
            message="Falha ao salvar a vaga",
            error=str(exc),
        )


async def run_extract_candidate_task(task_id: str, fields: dict[str, Any]) -> None:
    try:
        _progress(task_id, 10, "Preparando currículo")
        item_id = str(fields.get("item_id") or "")
        target_job_id = str(fields.get("target_job_id") or "").strip()
        provider = active_llm_provider(str(fields.get("llm_provider") or "") or None)
        llm = get_llm(provider)

        source_hint = str(fields.get("linkedin_url") or "").strip()
        if fields.get("resume_bytes"):
            _progress(task_id, 20, "Extraindo texto do arquivo enviado")
        elif str(fields.get("resume_text") or "").strip():
            _progress(task_id, 20, "Usando texto informado")
        elif source_hint:
            _progress(task_id, 20, "Lendo perfil do LinkedIn")
        else:
            _progress(task_id, 20, "Preparando origem do currículo")

        resolved = await resolve_resume_content(
            resume_text=str(fields.get("resume_text") or ""),
            resume_filename=str(fields.get("resume_filename") or ""),
            resume_bytes=fields.get("resume_bytes"),
            linkedin_url=source_hint,
        )
        full_resume_text = resolved["resume_text"]

        _progress(task_id, 40, f"Extraindo dados do currículo com LLM ({provider})")
        existing = candidates_store.get(item_id) if item_id else None
        candidate_id = item_id or new_id()
        extracted = await extract_candidate(full_resume_text, llm, candidate_id=candidate_id)
        payload = {
            "id": candidate_id,
            "name": extracted["name"],
            "city": extracted["city"],
            "reported_role": extracted["reported_role"],
            "resume_text": full_resume_text,
            "source_type": resolved["source_type"],
            "source_label": resolved["source_label"],
            "source_url": resolved["source_url"],
            "created_at": existing.get("created_at") if existing else now_iso(),
            "updated_at": now_iso(),
        }

        _progress(task_id, 60, "Salvando currículo")
        candidates_store.save(payload)

        redirect_url = f"/candidates/{payload['id']}"
        if target_job_id:
            _progress(task_id, 75, "Gerando score do candidato contra a vaga")
            await generate_score(target_job_id, payload["id"], llm_provider=provider)
            redirect_url = f"/scores?job_id={target_job_id}&candidate_id={payload['id']}"

        task_store.update(
            task_id,
            status="completed",
            progress=100,
            message="Currículo processado com sucesso",
            redirect_url=redirect_url,
        )
    except Exception as exc:
        task_store.update(
            task_id,
            status="failed",
            progress=100,
            message="Falha ao processar o currículo",
            error=str(exc),
        )


async def run_score_task(
    task_id: str,
    job_id: str,
    candidate_id: str,
    *,
    scoring_model: str | None = None,
    llm_provider: str | None = None,
) -> None:
    try:
        _progress(task_id, 15, "Carregando vaga e currículo")
        model = active_scoring_model(scoring_model)
        provider = active_llm_provider(llm_provider)
        _progress(task_id, 40, f"Avaliando aderência com LLM ({provider}, modelo {model})")
        result = await generate_score(
            job_id,
            candidate_id,
            scoring_model=model,
            llm_provider=provider,
        )
        if not result:
            raise ValueError("Vaga ou candidato não encontrado")

        task_store.update(
            task_id,
            status="completed",
            progress=100,
            message=f"Score gerado: {result.get('final_score')}% ({result.get('scoring_model_version', model)})",
            redirect_url=f"/scores?job_id={job_id}&candidate_id={candidate_id}",
        )
    except Exception as exc:
        task_store.update(
            task_id,
            status="failed",
            progress=100,
            message="Falha ao gerar o score",
            error=str(exc),
        )


@app.get("/")
def home(request: Request):
    jobs = jobs_store.read()
    candidates = candidates_store.read()
    scores = scores_store.read()
    status = _llm_status()
    usage = summarize_usage()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "jobs": jobs,
            "candidates": candidates,
            "scores": scores,
            **status,
            "llm_usage_totals": usage.get("totals") or {},
        },
    )


@app.get("/domains")
def domains():
    return redirect("/settings?tab=dominio")


@app.post("/domains/{domain_type}")
def save_domain(domain_type: str, name: str = Form(...), item_id: str = Form("")):
    domains_data = domains_store.read()
    if domain_type not in {"profiles", "seniorities"}:
        return redirect("/settings?tab=dominio")
    item = {"id": item_id or new_id(), "name": name.strip()}
    upsert(domains_data[domain_type], item)
    domains_store.write(domains_data)
    return redirect("/settings?tab=dominio&saved=1")


def _resolve_settings_tab(tab: str) -> str:
    if tab in {"sistema", "prompts", "dominio"}:
        return tab
    return "negocio"


def _settings_page_context(
    *,
    active_tab: str,
    saved: bool = False,
    error: str | None = None,
    prompt: str = "",
) -> dict[str, Any]:
    settings = get_business_settings()
    grouped: dict[str, list] = {}
    for item in settings["parameters"]:
        grouped.setdefault(item["category"], []).append(item)
    system = get_system_settings(reveal_secrets=False)
    prompt_groups = grouped_managed_prompts() if active_tab == "prompts" else {}
    selected_prompt = None
    if active_tab == "prompts":
        flat = [item for items in prompt_groups.values() for item in items]
        selected_id = prompt or (flat[0]["id"] if flat else "")
        if selected_id:
            try:
                selected_prompt = get_managed_prompt(selected_id)
            except Exception:
                selected_prompt = get_managed_prompt(flat[0]["id"]) if flat else None
    return {
        "title": "Parâmetros",
        "active_tab": active_tab,
        "settings": settings,
        "grouped": grouped,
        "value_types": VALUE_TYPES,
        "business_context": format_business_context(settings["parameters"]),
        "system": system,
        "domains": domains_store.read(),
        "prompt_groups": prompt_groups,
        "selected_prompt": selected_prompt,
        "saved": saved,
        "error": error,
    }


@app.get("/settings")
def settings_page(request: Request, saved: int = 0, tab: str = "negocio", prompt: str = ""):
    active_tab = _resolve_settings_tab(tab)
    return templates.TemplateResponse(
        request,
        "settings.html",
        _settings_page_context(active_tab=active_tab, saved=bool(saved), prompt=prompt),
    )


def _settings_error_response(request: Request, error: str, *, tab: str = "negocio", status_code: int = 400):
    active_tab = _resolve_settings_tab(tab)
    return templates.TemplateResponse(
        request,
        "settings.html",
        _settings_page_context(active_tab=active_tab, saved=False, error=error),
        status_code=status_code,
    )


@app.post("/settings")
async def save_settings_page(request: Request):
    form = await request.form()
    ids = form.getlist("id")
    keys = form.getlist("key")
    labels = form.getlist("label")
    values = form.getlist("value")
    value_types = form.getlist("value_type")
    categories = form.getlist("category")
    descriptions = form.getlist("description")
    count = len(ids)
    if not (count == len(keys) == len(labels) == len(values) == len(value_types) == len(categories) == len(descriptions)):
        return _settings_error_response(request, "Formulário inconsistente: recarregue a página e tente de novo.")

    parameters = []
    for index in range(count):
        item_id = str(ids[index])
        parameters.append(
            {
                "id": item_id,
                "key": str(keys[index]),
                "label": str(labels[index]),
                "value": values[index],
                "value_type": str(value_types[index]),
                "category": str(categories[index]),
                "description": str(descriptions[index]),
                "inject_in_prompts": f"inject_{item_id}" in form,
            }
        )
    try:
        save_business_settings({"parameters": parameters})
    except ValueError as exc:
        return _settings_error_response(request, str(exc), tab="negocio")
    return redirect("/settings?tab=negocio&saved=1")


@app.post("/settings/system")
async def save_system_settings_page(request: Request):
    form = await request.form()
    updates: dict[str, Any] = {}
    for key in form.keys():
        if key.startswith("sys_"):
            updates[key[4:]] = form.get(key)
    try:
        save_system_settings(updates)
    except ValueError as exc:
        return _settings_error_response(request, str(exc), tab="sistema")
    return redirect("/settings?tab=sistema&saved=1")


@app.post("/settings/parameters")
async def create_settings_parameter(
    request: Request,
    key: str = Form(...),
    label: str = Form(...),
    value: str = Form(...),
    value_type: str = Form("text"),
    category: str = Form("geral"),
    description: str = Form(""),
    inject_in_prompts: str = Form(""),
):
    try:
        upsert_business_parameter(
            {
                "key": key,
                "label": label,
                "value": value,
                "value_type": value_type,
                "category": category,
                "description": description,
                "inject_in_prompts": bool(inject_in_prompts),
            }
        )
    except ValueError as exc:
        return _settings_error_response(request, str(exc), tab="negocio")
    return redirect("/settings?tab=negocio&saved=1")


@app.post("/settings/parameters/{item_id}/delete")
async def remove_settings_parameter(request: Request, item_id: str):
    try:
        delete_business_parameter(item_id)
    except ValueError as exc:
        return _settings_error_response(request, str(exc), tab="negocio")
    return redirect("/settings?tab=negocio&saved=1")


@app.get("/api/v1/settings/business")
def api_get_business_settings():
    return get_business_settings()


@app.put("/api/v1/settings/business")
async def api_put_business_settings(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Payload JSON inválido")
    try:
        return save_business_settings(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/settings/business/parameters")
async def api_upsert_business_parameter(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Payload JSON inválido")
    try:
        return upsert_business_parameter(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/settings/business/parameters/{item_id}")
def api_delete_business_parameter(item_id: str):
    try:
        return delete_business_parameter(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/settings/system")
def api_get_system_settings():
    return get_system_settings(reveal_secrets=False)


@app.put("/api/v1/settings/system")
async def api_put_system_settings(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Payload JSON inválido")
    values = body.get("values") if isinstance(body.get("values"), dict) else body
    try:
        return save_system_settings(values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/settings/prompts/{prompt_id:path}/revert")
async def revert_prompt_settings_page(
    request: Request,
    prompt_id: str,
    version_id: str = Form(...),
):
    try:
        revert_prompt_version(prompt_id, version_id)
    except ValueError as exc:
        return _settings_error_response(request, str(exc), tab="prompts")
    return redirect(f"/settings?tab=prompts&prompt={prompt_id}&saved=1")


@app.post("/settings/prompts/{prompt_id:path}")
async def save_prompt_settings_page(
    request: Request,
    prompt_id: str,
    title: str = Form(...),
    description: str = Form(""),
    content: str = Form(...),
    note: str = Form(""),
):
    try:
        save_prompt_edit(prompt_id, content=content, title=title, description=description, note=note)
    except ValueError as exc:
        return _settings_error_response(request, str(exc), tab="prompts")
    except FileNotFoundError as exc:
        return _settings_error_response(request, str(exc), tab="prompts", status_code=404)
    return redirect(f"/settings?tab=prompts&prompt={prompt_id}&saved=1")


@app.get("/api/v1/settings/prompts")
def api_list_prompts():
    return {"items": list_managed_prompts()}


@app.post("/api/v1/settings/prompts/{prompt_id:path}/revert")
async def api_revert_prompt(prompt_id: str, request: Request):
    body = await request.json()
    if not isinstance(body, dict) or not body.get("version_id"):
        raise HTTPException(status_code=400, detail="Informe version_id")
    try:
        return revert_prompt_version(prompt_id, str(body["version_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/settings/prompts/{prompt_id:path}")
def api_get_prompt(prompt_id: str, version_id: str = ""):
    try:
        payload = get_managed_prompt(prompt_id, version_id=version_id or None)
        if version_id:
            payload["content"] = get_prompt_version_content(prompt_id, version_id)
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/v1/settings/prompts/{prompt_id:path}")
async def api_put_prompt(prompt_id: str, request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Payload JSON inválido")
    try:
        return save_prompt_edit(
            prompt_id,
            content=str(body.get("content") or ""),
            title=str(body.get("title") or "") or None,
            description=str(body.get("description") or ""),
            note=str(body.get("note") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/external-apis")
async def external_apis_page(request: Request):
    usage = await fetch_all_external_api_usage()
    return templates.TemplateResponse(
        request,
        "external_apis.html",
        {
            "title": "APIs Externas",
            "usage": usage,
        },
    )


@app.get("/api/v1/external-apis/usage")
async def api_external_apis_usage():
    return await fetch_all_external_api_usage()

@app.get("/jobs")
def list_jobs(request: Request):
    return templates.TemplateResponse(request, "jobs.html", {"jobs": jobs_store.read()})


@app.get("/jobs/new")
def new_job(request: Request):
    return job_form(request)


@app.get("/jobs/{job_id}/edit")
def edit_job(request: Request, job_id: str):
    job = find_by_id(jobs_store.read(), job_id)
    return job_form(request, job)


def job_form(request: Request, job: dict[str, Any] | None = None):
    job_data = job or {}
    analysis = normalize_job_analysis(job_data.get("analysis"))
    return templates.TemplateResponse(
        request,
        "job_form.html",
        {
            "job": job_data,
            "domains": domains_store.read(),
            "analysis": analysis,
            "is_edit": bool(job_data.get("id")),
            "llm_provider_default": active_llm_provider(),
        },
    )


@app.post("/jobs")
async def save_job(
    background_tasks: BackgroundTasks,
    item_id: str = Form(""),
    title: str = Form(...),
    description: str = Form(...),
    profile: str = Form(...),
    seniority: str = Form(...),
    job_description: str = Form(...),
    ideal_candidate_context: str = Form(""),
    compensation_type: str = Form(...),
    compensation_min: float = Form(...),
    compensation_max: float = Form(...),
    work_location: str = Form(...),
    save_mode: str = Form("reanalyse"),
    analysis_json: str = Form(""),
    llm_provider: str = Form(""),
):
    mode = (save_mode or "reanalyse").strip().lower()
    if mode not in {"save", "reanalyse"}:
        raise HTTPException(status_code=400, detail="Modo de salvamento inválido.")

    analysis: dict[str, Any] | None = None
    if mode == "save":
        try:
            parsed = json.loads(analysis_json or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="JSON de critérios inválido.") from exc
        analysis = normalize_job_analysis(parsed)

    fields = {
        "item_id": item_id,
        "title": title,
        "description": description,
        "profile": profile,
        "seniority": seniority,
        "job_description": job_description,
        "ideal_candidate_context": ideal_candidate_context,
        "compensation_type": compensation_type,
        "compensation_min": compensation_min,
        "compensation_max": compensation_max,
        "work_location": work_location,
        "save_mode": mode,
        "analysis": analysis,
        "llm_provider": active_llm_provider(llm_provider or None),
    }
    task = task_store.create("analyse_job" if mode == "reanalyse" else "save_job")
    background_tasks.add_task(run_analyse_job_task, task.task_id, fields)
    return JSONResponse(task.public())


@app.get("/jobs/{job_id}")
def job_detail(request: Request, job_id: str):
    job = find_by_id(jobs_store.read(), job_id)
    if not job:
        return redirect("/jobs")
    job = {**job, "analysis": normalize_job_analysis(job.get("analysis"))}
    return templates.TemplateResponse(request, "job_detail.html", {"job": job})


@app.get("/candidates")
def list_candidates(request: Request):
    return templates.TemplateResponse(request, "candidates.html", {"candidates": candidates_store.read()})


@app.get("/candidates/new")
def new_candidate(request: Request):
    return candidate_form(request)


@app.get("/candidates/{candidate_id}/edit")
def edit_candidate(request: Request, candidate_id: str):
    candidate = candidates_store.get(candidate_id)
    return candidate_form(request, candidate)


def candidate_form(request: Request, candidate: dict[str, Any] | None = None):
    return templates.TemplateResponse(
        request,
        "candidate_form.html",
        {
            "candidate": candidate or {},
            "jobs": jobs_store.read(),
            "llm_provider_default": active_llm_provider(),
        },
    )


@app.post("/candidates")
async def save_candidate(
    background_tasks: BackgroundTasks,
    item_id: str = Form(""),
    resume_text: str = Form(""),
    linkedin_url: str = Form(""),
    target_job_id: str = Form(""),
    llm_provider: str = Form(""),
    resume_file: UploadFile | None = File(None),
):
    resume_bytes: bytes | None = None
    resume_filename = ""
    if resume_file and resume_file.filename:
        resume_filename = resume_file.filename
        resume_bytes = await resume_file.read()
        if not resume_bytes:
            raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")

    has_source = bool(resume_bytes) or bool(linkedin_url.strip()) or bool(resume_text.strip())
    if not has_source:
        raise HTTPException(
            status_code=400,
            detail="Envie um PDF, informe o link do LinkedIn ou cole o texto do currículo.",
        )

    fields = {
        "item_id": item_id,
        "resume_text": resume_text,
        "linkedin_url": linkedin_url,
        "resume_filename": resume_filename,
        "resume_bytes": resume_bytes,
        "target_job_id": target_job_id,
        "llm_provider": active_llm_provider(llm_provider or None),
    }
    task = task_store.create("extract_candidate")
    background_tasks.add_task(run_extract_candidate_task, task.task_id, fields)
    return JSONResponse(task.public())


@app.get("/candidates/{candidate_id}")
def candidate_detail(request: Request, candidate_id: str):
    candidate = candidates_store.get(candidate_id)
    if not candidate:
        return redirect("/candidates")
    return templates.TemplateResponse(request, "candidate_detail.html", {"candidate": candidate})


@app.get("/scores")
def scores(request: Request, job_id: str = "", candidate_id: str = ""):
    all_scores = scores_store.read()
    selected = None
    chart_data = None
    if job_id and candidate_id:
        selected = scores_store.find(job_id, candidate_id)
        if selected:
            chart_data = build_score_chart_data(selected.get("items") or [])
            breakdown = selected.get("score_breakdown") or {}
            if breakdown.get("dimensions"):
                chart_data["breakdown"] = {
                    "labels": list(breakdown["dimensions"].keys()),
                    "values": list(breakdown["dimensions"].values()),
                    "weights": breakdown.get("weights") or {},
                }
    return templates.TemplateResponse(
        request,
        "scores.html",
        {
            "request": request,
            "jobs": jobs_store.read(),
            "candidates": candidates_store.read(),
            "scores": all_scores,
            "selected": selected,
            "chart_data": chart_data,
            "job_id": job_id,
            "candidate_id": candidate_id,
            "scoring_model_default": SCORING_MODEL,
            "llm_provider_default": active_llm_provider(),
        },
    )


@app.post("/scores")
async def create_score(
    background_tasks: BackgroundTasks,
    job_id: str = Form(...),
    candidate_id: str = Form(...),
    scoring_model: str = Form(""),
    llm_provider: str = Form(""),
):
    model = active_scoring_model(scoring_model or None)
    provider = active_llm_provider(llm_provider or None)
    task = task_store.create("score")
    background_tasks.add_task(
        run_score_task,
        task.task_id,
        job_id,
        candidate_id,
        scoring_model=model,
        llm_provider=provider,
    )
    return JSONResponse(task.public())


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    """Poll async task status. Task IDs are unguessable UUIDs (MVP).

    Auth is intentionally not required so the HTML UI can poll after form POSTs.
    Prefer scoping network exposure; use PROFESSIONAL_PROFILE_API_KEY on /api/gpt.
    """
    task = task_store.get(task_id)
    if not task:
        return JSONResponse({"detail": "Task not found."}, status_code=404)
    return task.public()


@app.get("/api/llm/usage")
def llm_usage_summary(since: str = ""):
    return summarize_usage(since.strip() or None)


async def generate_score(
    job_id: str,
    candidate_id: str,
    *,
    scoring_model: str | None = None,
    llm_provider: str | None = None,
) -> dict[str, Any] | None:
    job = find_by_id(jobs_store.read(), job_id)
    candidate = candidates_store.get(candidate_id)
    if not job or not candidate:
        return None

    llm = get_llm(llm_provider)
    result = await score_candidate(job, candidate, llm, scoring_model=scoring_model)
    result["id"] = f"{job_id}_{candidate_id}"
    result["created_at"] = now_iso()
    return scores_store.save(result)
