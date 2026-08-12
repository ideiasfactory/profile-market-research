from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import markdown as markdown_lib
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.compensation import router as compensation_router
from app.env_loader import load_app_env
from app.gpt import router as gpt_router
from app.llm import LocalLLM
from app.logging_config import configure_logging
from app.resume_ingest import resolve_resume_content
from app.scoring_config import SCORING_MODEL, active_scoring_model
from app.services import analyse_job, build_score_chart_data, extract_candidate, normalize_job_analysis, score_candidate
from app.storage import candidates_store, domains_store, find_by_id, jobs_store, new_id, scores_store, upsert
from app.tasks import task_store


load_app_env()
configure_logging()

app = FastAPI(title="Professional Profile Analyser")
app.include_router(compensation_router)
app.include_router(gpt_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["markdown"] = lambda value: markdown_lib.markdown(
    value or "",
    extensions=["extra", "sane_lists", "nl2br"],
)
templates.env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)
llm = LocalLLM()


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
            _progress(task_id, 35, "Analisando vaga com LLM (pode levar alguns segundos)")
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

        _progress(task_id, 40, "Extraindo dados do currículo com LLM")
        existing = candidates_store.get(item_id) if item_id else None
        extracted = await extract_candidate(full_resume_text, llm)
        payload = {
            "id": item_id or new_id(),
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
            await generate_score(target_job_id, payload["id"])
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
) -> None:
    try:
        _progress(task_id, 15, "Carregando vaga e currículo")
        model = active_scoring_model(scoring_model)
        _progress(task_id, 40, f"Avaliando aderência com LLM (modelo {model})")
        result = await generate_score(job_id, candidate_id, scoring_model=model)
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
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "jobs": jobs,
            "candidates": candidates,
            "scores": scores,
            "llm_configured": llm.configured,
        },
    )


@app.get("/domains")
def domains(request: Request):
    return templates.TemplateResponse(request, "domains.html", {"domains": domains_store.read()})


@app.post("/domains/{domain_type}")
def save_domain(domain_type: str, name: str = Form(...), item_id: str = Form("")):
    domains_data = domains_store.read()
    if domain_type not in {"profiles", "seniorities"}:
        return redirect("/domains")
    item = {"id": item_id or new_id(), "name": name.strip()}
    upsert(domains_data[domain_type], item)
    domains_store.write(domains_data)
    return redirect("/domains")


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
        {"candidate": candidate or {}, "jobs": jobs_store.read()},
    )


@app.post("/candidates")
async def save_candidate(
    background_tasks: BackgroundTasks,
    item_id: str = Form(""),
    resume_text: str = Form(""),
    linkedin_url: str = Form(""),
    target_job_id: str = Form(""),
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
        },
    )


@app.post("/scores")
async def create_score(
    background_tasks: BackgroundTasks,
    job_id: str = Form(...),
    candidate_id: str = Form(...),
    scoring_model: str = Form(""),
):
    model = active_scoring_model(scoring_model or None)
    task = task_store.create("score")
    background_tasks.add_task(run_score_task, task.task_id, job_id, candidate_id, scoring_model=model)
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


async def generate_score(
    job_id: str,
    candidate_id: str,
    *,
    scoring_model: str | None = None,
) -> dict[str, Any] | None:
    job = find_by_id(jobs_store.read(), job_id)
    candidate = candidates_store.get(candidate_id)
    if not job or not candidate:
        return None

    result = await score_candidate(job, candidate, llm, scoring_model=scoring_model)
    result["id"] = f"{job_id}_{candidate_id}"
    result["created_at"] = now_iso()
    return scores_store.save(result)
