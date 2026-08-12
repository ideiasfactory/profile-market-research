"""GPT Actions API resource (`/api/gpt`).

JSON surface dedicated to the Professional Profile Analyst Custom GPT.
Read-oriented endpoints return compact domain objects. Mutations that
trigger LLM work (evaluate) or Compensation Intelligence research return
async Task handles (poll GET /api/gpt/tasks/{task_id}). Compensation
routes reuse the same auth as other GPT Actions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.compensation.domain.schemas import CompensationResearchRequest
from app.compensation.services.history import list_cached_research, load_cached_research
from app.compensation.services.job_prefill import map_job_to_compensation_prefill
from app.compensation.services.orchestrator import CompensationResearchOrchestrator
from app.scoring_config import SCORING_MODEL, active_scoring_model
from app.llm import active_llm_provider
from app.services import normalize_job_analysis
from app.storage import candidates_store, find_by_id, jobs_store, scores_store
from app.tasks import task_store


router = APIRouter(
    prefix="/api/gpt",
    tags=["gpt"],
    dependencies=[Depends(require_api_key)],
)


class EvaluateRequest(BaseModel):
    job_id: str = Field(..., description="Job identifier to evaluate against.")
    candidate_id: str = Field(..., description="Candidate identifier to evaluate.")
    scoring_model: str | None = Field(
        default=None,
        description="Optional scoring model override: v1 or v2. Defaults to server SCORING_MODEL.",
    )
    llm_provider: str | None = Field(
        default=None,
        description="Optional LLM provider override: local or openai. Defaults to server LLM_PROVIDER.",
    )


def _normalize_q(value: str | None) -> str:
    return (value or "").strip().lower()


def _matches_query(haystack: str, query: str) -> bool:
    if not query:
        return True
    return query in (haystack or "").lower()


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job.get("id"),
        "title": job.get("title"),
        "description": job.get("description"),
        "profile": job.get("profile"),
        "seniority": job.get("seniority"),
        "work_location": job.get("work_location"),
        "compensation_type": job.get("compensation_type"),
        "compensation_min": job.get("compensation_min"),
        "compensation_max": job.get("compensation_max"),
        "updated_at": job.get("updated_at"),
        "created_at": job.get("created_at"),
        "has_analysis": bool(job.get("analysis")),
    }


def _job_detail(job: dict[str, Any]) -> dict[str, Any]:
    analysis = normalize_job_analysis(job.get("analysis"))
    return {
        **_job_summary(job),
        "job_description": job.get("job_description"),
        "ideal_candidate_context": job.get("ideal_candidate_context") or "",
        "analysis": {
            "version": analysis.get("version"),
            "role_intent": analysis.get("role_intent"),
            "role_expectations": analysis.get("role_expectations"),
            "context_signals": analysis.get("context_signals") or [],
            "must_have": analysis.get("must_have") or [],
            "core_skills": analysis.get("core_skills") or [],
            "supporting_skills": analysis.get("supporting_skills") or [],
            "differentials": analysis.get("differentials") or [],
            "soft_skills": analysis.get("soft_skills") or [],
            "skill_groups": analysis.get("skill_groups") or [],
        },
    }


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate.get("id"),
        "name": candidate.get("name"),
        "city": candidate.get("city"),
        "reported_role": candidate.get("reported_role"),
        "source_type": candidate.get("source_type"),
        "source_label": candidate.get("source_label"),
        "updated_at": candidate.get("updated_at"),
        "created_at": candidate.get("created_at"),
    }


def _candidate_detail(candidate: dict[str, Any], *, include_resume: bool) -> dict[str, Any]:
    payload = _candidate_summary(candidate)
    if include_resume:
        payload["resume_text"] = candidate.get("resume_text") or ""
    else:
        text = str(candidate.get("resume_text") or "")
        payload["resume_available"] = bool(text.strip())
        payload["resume_length"] = len(text)
    return payload


def _evaluation_summary(score: dict[str, Any]) -> dict[str, Any]:
    audit = score.get("audit") if isinstance(score.get("audit"), dict) else {}
    usage = audit.get("usage") if isinstance(audit.get("usage"), dict) else {}
    summary = {
        "evaluation_id": score.get("id"),
        "job_id": score.get("job_id"),
        "candidate_id": score.get("candidate_id"),
        "job_title": score.get("job_title"),
        "candidate_name": score.get("candidate_name"),
        "final_score": score.get("final_score"),
        "verdict_label": score.get("verdict_label"),
        "scoring_model_version": score.get("scoring_model_version") or "v1",
        "method": score.get("method"),
        "created_at": score.get("created_at"),
        "llm_provider": score.get("llm_provider") or audit.get("llm_provider"),
        "llm_model": score.get("llm_model") or audit.get("llm_model"),
    }
    if score.get("is_history") or score.get("history_id"):
        summary["is_history"] = True
        summary["history_id"] = score.get("history_id") or score.get("id")
        summary["score_id"] = score.get("score_id") or (
            f"{score.get('job_id')}_{score.get('candidate_id')}"
        )
        if score.get("archived_at"):
            summary["archived_at"] = score.get("archived_at")
    cost = score.get("estimated_cost_usd")
    if cost is None:
        cost = usage.get("estimated_cost_usd")
    tokens = score.get("total_tokens")
    if tokens is None:
        tokens = usage.get("total_tokens")
    if cost is not None:
        summary["estimated_cost_usd"] = cost
    if tokens is not None:
        summary["total_tokens"] = tokens
    return summary


def _evaluation_detail(score: dict[str, Any], *, include_items: bool) -> dict[str, Any]:
    payload = {
        **_evaluation_summary(score),
        "verdict": score.get("verdict"),
        "profile_summary": score.get("profile_summary"),
        "score_breakdown": score.get("score_breakdown"),
        "must_have_coverage": score.get("must_have_coverage"),
        "critical_gaps": score.get("critical_gaps") or [],
        "strengths": score.get("strengths") or [],
        "gaps": score.get("gaps") or [],
        "interview_validation": score.get("interview_validation") or [],
        "role_fit": score.get("role_fit"),
        "context_fit": score.get("context_fit"),
        "group_scores": score.get("group_scores") or [],
        "candidate": {
            "id": score.get("candidate_id"),
            "name": score.get("candidate_name"),
        },
        "job": {
            "id": score.get("job_id"),
            "title": score.get("job_title"),
        },
    }
    if include_items:
        payload["items"] = score.get("items") or []
    return payload


def _history_summaries(job_id: str, candidate_id: str) -> list[dict[str, Any]]:
    return [
        _evaluation_summary({**entry, "is_history": True, "history_id": entry.get("id")})
        for entry in scores_store.history_for(job_id, candidate_id)
    ]


@router.get(
    "/jobs",
    operation_id="listJobs",
    summary="List jobs",
    description="List persisted jobs. Optional q filters by title, description, profile, or id. Use before answering questions about stored opportunities.",
)
def list_jobs(q: str | None = Query(default=None, description="Case-insensitive search text")) -> dict[str, Any]:
    query = _normalize_q(q)
    jobs = []
    for job in jobs_store.read():
        haystack = " ".join(
            str(job.get(key) or "")
            for key in ("id", "title", "description", "profile", "seniority")
        )
        if _matches_query(haystack, query):
            jobs.append(_job_summary(job))
    return {"count": len(jobs), "jobs": jobs}


@router.get(
    "/jobs/{job_id}",
    operation_id="getJob",
    summary="Get job",
    description="Retrieve a job including job analysis (role intent, must-haves, skill tiers). Prefer this over conversational memory for stored jobs.",
)
def get_job(job_id: str) -> dict[str, Any]:
    job = find_by_id(jobs_store.read(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_detail(job)


@router.get(
    "/candidates",
    operation_id="listCandidates",
    summary="List candidates",
    description="List candidate index entries (no full resume text). Optional q filters by name, role, city, or id.",
)
def list_candidates(
    q: str | None = Query(default=None, description="Case-insensitive search text"),
) -> dict[str, Any]:
    query = _normalize_q(q)
    candidates = []
    for candidate in candidates_store.read():
        haystack = " ".join(
            str(candidate.get(key) or "")
            for key in ("id", "name", "reported_role", "city")
        )
        if _matches_query(haystack, query):
            candidates.append(_candidate_summary(candidate))
    return {"count": len(candidates), "candidates": candidates}


@router.get(
    "/candidates/{candidate_id}",
    operation_id="getCandidate",
    summary="Get candidate",
    description="Retrieve a candidate. Set include_resume=true only when evidence inspection is required. Never invent candidates.",
)
def get_candidate(
    candidate_id: str,
    include_resume: bool = Query(
        default=False,
        description="Include full resume_text when true. Default false for privacy minimization.",
    ),
) -> dict[str, Any]:
    candidate = candidates_store.get(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return _candidate_detail(candidate, include_resume=include_resume)


@router.get(
    "/jobs/{job_id}/candidates",
    operation_id="listJobCandidates",
    summary="List candidates evaluated for a job",
    description="Return candidates that have a persisted evaluation for the given job_id.",
)
def list_job_candidates(job_id: str) -> dict[str, Any]:
    job = find_by_id(jobs_store.read(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    by_candidate: dict[str, dict[str, Any]] = {}
    for entry in scores_store.read():
        if entry.get("job_id") != job_id:
            continue
        cid = str(entry.get("candidate_id") or "")
        if not cid:
            continue
        candidate = candidates_store.get(cid) or {
            "id": cid,
            "name": entry.get("candidate_name"),
        }
        by_candidate[cid] = {
            **_candidate_summary(candidate),
            "evaluation_id": entry.get("id"),
            "final_score": entry.get("final_score"),
            "verdict_label": entry.get("verdict_label"),
            "scoring_model_version": entry.get("scoring_model_version"),
        }

    items = list(by_candidate.values())
    return {
        "job": {"id": job.get("id"), "title": job.get("title")},
        "count": len(items),
        "candidates": items,
    }


@router.get(
    "/evaluations",
    operation_id="listEvaluations",
    summary="List evaluations",
    description="List persisted evaluations (scores). Filter by job_id and/or candidate_id.",
)
def list_evaluations(
    job_id: str | None = Query(default=None),
    candidate_id: str | None = Query(default=None),
) -> dict[str, Any]:
    items = []
    for entry in scores_store.read():
        if job_id and entry.get("job_id") != job_id:
            continue
        if candidate_id and entry.get("candidate_id") != candidate_id:
            continue
        items.append(_evaluation_summary(entry))
    return {"count": len(items), "evaluations": items}


@router.get(
    "/jobs/{job_id}/evaluations",
    operation_id="listJobEvaluations",
    summary="List evaluations for a job",
    description="List all persisted evaluations for a specific job.",
)
def list_job_evaluations(job_id: str) -> dict[str, Any]:
    job = find_by_id(jobs_store.read(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    items = [
        _evaluation_summary(entry)
        for entry in scores_store.read()
        if entry.get("job_id") == job_id
    ]
    return {
        "job": {"id": job.get("id"), "title": job.get("title")},
        "count": len(items),
        "evaluations": items,
    }


@router.get(
    "/evaluations/{evaluation_id}",
    operation_id="getEvaluation",
    summary="Get evaluation",
    description=(
        "Retrieve a persisted evaluation by id (format: {job_id}_{candidate_id}) "
        "or a historical run id from score history. "
        "Use include_items=true for skill-level evidence. Connected mode must treat "
        "final_score as authoritative — do not recalculate. "
        "Use include_history=true on a latest evaluation to list archived runs for the pair."
    ),
)
def get_evaluation(
    evaluation_id: str,
    include_items: bool = Query(
        default=False,
        description="Include per-skill items with evidence when true.",
    ),
    include_history: bool = Query(
        default=False,
        description="When resolving the latest pair evaluation, include archived runs.",
    ),
) -> dict[str, Any]:
    score = scores_store.get_any(evaluation_id)
    if not score:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    payload = _evaluation_detail(score, include_items=include_items)
    if include_history and not score.get("is_history"):
        job_id = str(score.get("job_id") or "")
        candidate_id = str(score.get("candidate_id") or "")
        if job_id and candidate_id:
            payload["history"] = _history_summaries(job_id, candidate_id)
    return payload


@router.get(
    "/jobs/{job_id}/evaluations/{candidate_id}",
    operation_id="getJobCandidateEvaluation",
    summary="Get evaluation by job and candidate",
    description=(
        "Retrieve the latest persisted evaluation for a job × candidate pair. "
        "Optional include_history returns archived runs for Local vs OpenAI comparison."
    ),
)
def get_job_candidate_evaluation(
    job_id: str,
    candidate_id: str,
    include_items: bool = Query(default=False),
    include_history: bool = Query(default=False),
) -> dict[str, Any]:
    score = scores_store.find(job_id, candidate_id)
    if not score:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    payload = _evaluation_detail(score, include_items=include_items)
    if include_history:
        payload["history"] = _history_summaries(job_id, candidate_id)
    return payload


@router.post(
    "/evaluations",
    operation_id="evaluateCandidate",
    summary="Create or re-evaluate candidate against job",
    description=(
        "WRITE operation. Starts an async evaluation using the application scoring engine "
        "(default v2). Returns a Task. Poll GET /api/gpt/tasks/{task_id}. "
        "Execute only when the user clearly requests evaluation or re-evaluation."
    ),
)
async def evaluate_candidate(
    body: EvaluateRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    from app.main import run_score_task

    job = find_by_id(jobs_store.read(), body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    candidate = candidates_store.get(body.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    model = active_scoring_model(body.scoring_model)
    provider = active_llm_provider(body.llm_provider)
    task = task_store.create("score")
    background_tasks.add_task(
        run_score_task,
        task.task_id,
        body.job_id,
        body.candidate_id,
        scoring_model=model,
        llm_provider=provider,
    )
    payload = task.public()
    payload["scoring_model"] = model
    payload["default_scoring_model"] = SCORING_MODEL
    payload["llm_provider"] = provider
    payload["default_llm_provider"] = active_llm_provider()
    return payload


@router.get(
    "/tasks/{task_id}",
    operation_id="getTask",
    summary="Poll async task",
    description=(
        "Poll analyse/extract/score/compensation_research task status for GPT Actions. "
        "When completed after evaluateCandidate, fetch the evaluation via getJobCandidateEvaluation. "
        "When completed after researchCompensationAsync, use task.result as the compensation research "
        "payload (market stats, confidence, sources, observations, warnings)."
    ),
)
def get_task(task_id: str) -> dict[str, Any]:
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task.public()


def _compensation_payload_for_gpt(
    payload: dict[str, Any],
    *,
    include_observations: bool,
) -> dict[str, Any]:
    """Return research JSON; optionally omit bulky observation rows for GPT Actions."""
    if include_observations:
        return payload
    trimmed = dict(payload)
    observations = trimmed.get("observations") or []
    trimmed["observations"] = []
    trimmed["observations_omitted"] = True
    trimmed["observations_count"] = len(observations) if isinstance(observations, list) else 0
    return trimmed


@router.get(
    "/compensation/prefill/{job_id}",
    operation_id="prefillCompensationFromJob",
    summary="Prefill compensation research from a job",
    description=(
        "Map a stored job (title, seniority, work location, analysis skills, compensation metadata) "
        "into a CompensationResearchRequest-shaped prefill. Prefer this when the user discusses an "
        "open job already in the system before starting research."
    ),
)
def prefill_compensation_from_job(job_id: str) -> dict[str, Any]:
    job = find_by_id(jobs_store.read(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return map_job_to_compensation_prefill(job)


@router.get(
    "/compensation/history",
    operation_id="listCompensationHistory",
    summary="List cached compensation research",
    description=(
        "List compact summaries of cached Compensation Intelligence research runs. "
        "Use before re-running research when a recent cache may suffice."
    ),
)
def list_compensation_history() -> dict[str, Any]:
    items = list_cached_research()
    return {"count": len(items), "items": items}


@router.get(
    "/compensation/history/{cache_key}",
    operation_id="getCompensationHistoryItem",
    summary="Get cached compensation research",
    description=(
        "Load a cached research payload by cache_key. "
        "By default observations are omitted (observations_omitted=true) to keep Action payloads small; "
        "set include_observations=true when citing individual salary evidence rows."
    ),
)
def get_compensation_history_item(
    cache_key: str,
    include_observations: bool = Query(
        default=False,
        description="Include full observation rows when true. Default false for compact GPT payloads.",
    ),
) -> dict[str, Any]:
    payload = load_cached_research(cache_key)
    if payload is None:
        raise HTTPException(status_code=404, detail="Compensation research not found in cache.")
    return _compensation_payload_for_gpt(payload, include_observations=include_observations)


@router.post(
    "/compensation/research/async",
    operation_id="researchCompensationAsync",
    summary="Start async compensation / market-pay research",
    description=(
        "WRITE-like operation (external search + cache). Preferred path when the client can poll: "
        "long-running Compensation Intelligence research. Returns a Task (kind=compensation_research). "
        "Poll getTask until completed/failed; on success, task.result holds the research payload. "
        "Cache policy: leave force_refresh=false (default) unless the user explicitly asks to ignore "
        "cache / force a new research. Execute only when the user clearly asks for market pay / "
        "compensation research. Never invent salaries — cite only returned market stats, sources, "
        "observations, and warnings."
    ),
)
async def research_compensation_async(
    body: CompensationResearchRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    from app.api.compensation import run_compensation_research_task

    task = task_store.create("compensation_research")
    background_tasks.add_task(run_compensation_research_task, task.task_id, body)
    return task.public()


@router.post(
    "/compensation/research/wait",
    operation_id="researchCompensationWait",
    summary="Run compensation research and wait for the final result",
    description=(
        "WRITE-like convenience for conversational frontends (e.g. Open WebUI) that struggle with "
        "async Task + poll loops. Runs Compensation Intelligence research and returns the final "
        "payload in one HTTP call. Cache policy: force_refresh defaults to false — reuse cache "
        "unless the user explicitly asks to ignore cache / force refresh. Prefer this over raw "
        "async+poll when the tool layer cannot poll reliably; prefer async+getTask when it can. "
        "Never invent salaries from training data."
    ),
)
async def research_compensation_wait(
    body: CompensationResearchRequest,
    include_observations: bool = Query(
        default=True,
        description="Include observation rows in the response. Set false for a compact summary.",
    ),
) -> dict[str, Any]:
    result = await CompensationResearchOrchestrator().research(body)
    payload = result.model_dump(mode="json")
    return _compensation_payload_for_gpt(payload, include_observations=include_observations)


@router.post(
    "/compensation/research",
    operation_id="researchCompensation",
    summary="Sync compensation / market-pay research",
    description=(
        "WRITE-like operation. Runs Compensation Intelligence research synchronously and returns the "
        "full result. Prefer researchCompensationAsync (+ getTask) when the client can poll, or "
        "researchCompensationWait for Open WebUI-style single-shot tools. Cache policy: "
        "force_refresh defaults to false. Never invent salaries from training data."
    ),
)
async def research_compensation_sync(
    body: CompensationResearchRequest,
    include_observations: bool = Query(
        default=True,
        description="Include observation rows in the response. Set false for a compact summary.",
    ),
) -> dict[str, Any]:
    result = await CompensationResearchOrchestrator().research(body)
    payload = result.model_dump(mode="json")
    return _compensation_payload_for_gpt(payload, include_observations=include_observations)
