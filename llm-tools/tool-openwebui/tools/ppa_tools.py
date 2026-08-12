"""
title: Professional Profile Analyser
author: PPA
author_url: https://github.com/flaviolopes/professional_profile_analyser
version: 0.1.0
license: MIT
description: Calls PPA `/api/gpt/*` (jobs, candidates, evaluations, compensation). Prefer Global Tool Server (OpenAPI) when available; use this Python tool under Workspace → Ferramentas as a fallback.
required_open_webui_version: 0.4.0
"""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        ppa_base_url: str = Field(
            default="http://host.docker.internal:8000",
            description=(
                "PPA base URL as seen from the Open WebUI process. "
                "Docker → host: http://host.docker.internal:8000. "
                "Open WebUI on host → http://127.0.0.1:8000."
            ),
        )
        api_key: str = Field(
            default="",
            description=(
                "Optional PROFESSIONAL_PROFILE_API_KEY. "
                "Sent as Bearer and X-API-Key when non-empty."
            ),
        )
        timeout_seconds: int = Field(
            default=120,
            description="HTTP timeout for PPA calls (raise for research/wait).",
        )
        pass

    def __init__(self) -> None:
        self.valves = self.Valves()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        key = (self.valves.api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
            headers["X-API-Key"] = key
        return headers

    def _url(self, path: str, query: Optional[dict[str, Any]] = None) -> str:
        base = (self.valves.ppa_base_url or "").rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        url = f"{base}{path}"
        if query:
            filtered = {
                k: ("true" if v is True else "false" if v is False else v)
                for k, v in query.items()
                if v is not None
            }
            if filtered:
                url = f"{url}?{urlencode(filtered)}"
        return url

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> str:
        url = self._url(path, query)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method=method.upper())
        timeout = max(5, int(self.valves.timeout_seconds or 120))
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return raw or json.dumps({"ok": True, "status": resp.status})
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return json.dumps(
                {
                    "error": True,
                    "status": exc.code,
                    "url": url,
                    "detail": detail or str(exc),
                },
                ensure_ascii=False,
            )
        except URLError as exc:
            return json.dumps(
                {
                    "error": True,
                    "url": url,
                    "detail": (
                        f"Connection failed ({exc.reason}). "
                        "If Open WebUI runs in Docker, set Valves.ppa_base_url to "
                        "http://host.docker.internal:8000 (not 127.0.0.1)."
                    ),
                },
                ensure_ascii=False,
            )
        except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
            return json.dumps(
                {"error": True, "url": url, "detail": str(exc)},
                ensure_ascii=False,
            )

    def list_jobs(self, q: Optional[str] = None) -> str:
        """
        List jobs stored in Professional Profile Analyser.
        Resolve job names to IDs before other job-scoped calls.
        :param q: Optional case-insensitive search text
        """
        return self._request("GET", "/api/gpt/jobs", query={"q": q})

    def get_job(self, job_id: str) -> str:
        """
        Get one job by id.
        :param job_id: Job UUID / id from list_jobs
        """
        return self._request("GET", f"/api/gpt/jobs/{job_id}")

    def list_candidates(self, q: Optional[str] = None) -> str:
        """
        List candidates stored in PPA.
        :param q: Optional case-insensitive search text
        """
        return self._request("GET", "/api/gpt/candidates", query={"q": q})

    def get_candidate(self, candidate_id: str, include_resume: bool = False) -> str:
        """
        Get one candidate by id.
        :param candidate_id: Candidate id from list_candidates
        :param include_resume: Include raw resume text when true
        """
        return self._request(
            "GET",
            f"/api/gpt/candidates/{candidate_id}",
            query={"include_resume": include_resume},
        )

    def list_job_candidates(self, job_id: str) -> str:
        """
        List candidates associated with a job.
        :param job_id: Job id
        """
        return self._request("GET", f"/api/gpt/jobs/{job_id}/candidates")

    def get_evaluation(
        self, evaluation_id: str, include_items: bool = True
    ) -> str:
        """
        Get a persisted evaluation by id.
        :param evaluation_id: Evaluation id
        :param include_items: Include score item breakdown
        """
        return self._request(
            "GET",
            f"/api/gpt/evaluations/{evaluation_id}",
            query={"include_items": include_items},
        )

    def get_job_candidate_evaluation(self, job_id: str, candidate_id: str) -> str:
        """
        Get the latest evaluation for a job + candidate pair.
        :param job_id: Job id
        :param candidate_id: Candidate id
        """
        return self._request(
            "GET", f"/api/gpt/jobs/{job_id}/evaluations/{candidate_id}"
        )

    def evaluate_candidate(
        self,
        job_id: str,
        candidate_id: str,
        scoring_model: Optional[str] = None,
    ) -> str:
        """
        Start an async evaluation (persists). Poll get_task until completed/failed.
        Only call when the user clearly asks to evaluate and persist.
        :param job_id: Job id
        :param candidate_id: Candidate id
        :param scoring_model: Optional v1 or v2 (server default if omitted)
        """
        body: dict[str, Any] = {
            "job_id": job_id,
            "candidate_id": candidate_id,
        }
        if scoring_model:
            body["scoring_model"] = scoring_model
        return self._request(
            "POST",
            "/api/gpt/evaluations",
            body=body,
        )

    def get_task(self, task_id: str) -> str:
        """
        Poll an async task (evaluation or compensation research).
        When status is completed, use task.result.
        :param task_id: Task id from evaluate_candidate or research_compensation_async
        """
        return self._request("GET", f"/api/gpt/tasks/{task_id}")

    def prefill_compensation_from_job(self, job_id: str) -> str:
        """
        Prefill a compensation research request from a stored job.
        :param job_id: Job id
        """
        return self._request("GET", f"/api/gpt/compensation/prefill/{job_id}")

    def list_compensation_history(self) -> str:
        """List recent compensation research cache entries."""
        return self._request("GET", "/api/gpt/compensation/history")

    def get_compensation_history_item(
        self, cache_key: str, include_observations: bool = True
    ) -> str:
        """
        Get one compensation history / cache item.
        :param cache_key: Cache key from list_compensation_history
        :param include_observations: Include observation details
        """
        return self._request(
            "GET",
            f"/api/gpt/compensation/history/{cache_key}",
            query={"include_observations": include_observations},
        )

    def research_compensation_wait(
        self,
        profile: str,
        skills: Optional[list[str]] = None,
        seniority: Optional[str] = None,
        allocation_model: str = "remote",
        country: Optional[str] = None,
        state: Optional[str] = None,
        city: Optional[str] = None,
        target_contract: str = "PJ",
        force_refresh: bool = False,
        source_job_id: Optional[str] = None,
        include_observations: bool = True,
    ) -> str:
        """
        Preferred compensation path for Open WebUI: one HTTP call, final result.
        Cache policy: force_refresh MUST stay false unless the user explicitly asks
        to ignore cache / force a new research (e.g. "ignore o cache", "force refresh").
        Never invent salaries — cite only returned market/sources/observations/warnings.
        :param profile: Role / profile title (required)
        :param skills: Optional skill list
        :param seniority: Optional seniority label
        :param allocation_model: onsite | hybrid | remote
        :param country: Location country (e.g. BR)
        :param state: Location state / region
        :param city: Location city
        :param target_contract: CLT or PJ
        :param force_refresh: Default false — use cache unless user explicitly asks otherwise
        :param source_job_id: Optional link to a stored job id
        :param include_observations: Include observation details in the response
        """
        location: dict[str, Any] = {}
        if country:
            location["country"] = country
        if state:
            location["state"] = state
        if city:
            location["city"] = city
        body: dict[str, Any] = {
            "profile": profile,
            "skills": skills or [],
            "allocation_model": allocation_model,
            "target_contract": target_contract,
            "force_refresh": bool(force_refresh),
        }
        if seniority:
            body["seniority"] = seniority
        if location:
            body["location"] = location
        if source_job_id:
            body["source_job_id"] = source_job_id
        return self._request(
            "POST",
            "/api/gpt/compensation/research/wait",
            query={"include_observations": include_observations},
            body=body,
        )

    def research_compensation_async(
        self,
        profile: str,
        skills: Optional[list[str]] = None,
        seniority: Optional[str] = None,
        allocation_model: str = "remote",
        country: Optional[str] = None,
        state: Optional[str] = None,
        city: Optional[str] = None,
        target_contract: str = "PJ",
        force_refresh: bool = False,
        source_job_id: Optional[str] = None,
    ) -> str:
        """
        Start async compensation research. Poll get_task until completed/failed.
        Prefer research_compensation_wait when polling is unreliable.
        force_refresh defaults to false (use cache) unless the user explicitly asks otherwise.
        :param profile: Role / profile title (required)
        :param skills: Optional skill list
        :param seniority: Optional seniority label
        :param allocation_model: onsite | hybrid | remote
        :param country: Location country
        :param state: Location state / region
        :param city: Location city
        :param target_contract: CLT or PJ
        :param force_refresh: Default false
        :param source_job_id: Optional stored job id
        """
        location: dict[str, Any] = {}
        if country:
            location["country"] = country
        if state:
            location["state"] = state
        if city:
            location["city"] = city
        body: dict[str, Any] = {
            "profile": profile,
            "skills": skills or [],
            "allocation_model": allocation_model,
            "target_contract": target_contract,
            "force_refresh": bool(force_refresh),
        }
        if seniority:
            body["seniority"] = seniority
        if location:
            body["location"] = location
        if source_job_id:
            body["source_job_id"] = source_job_id
        return self._request(
            "POST",
            "/api/gpt/compensation/research/async",
            body=body,
        )
