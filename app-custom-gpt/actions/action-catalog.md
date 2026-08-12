# Action Catalog

custom_gpt_version: 0.2.0  
actions_version: 1.1

## Implemented (Actions OpenAPI)

| operationId | Method | Path | Class | Notes |
|-------------|--------|------|-------|-------|
| listJobs | GET | `/api/gpt/jobs` | READ | Optional `q` |
| getJob | GET | `/api/gpt/jobs/{job_id}` | READ | Includes analysis |
| listCandidates | GET | `/api/gpt/candidates` | READ | Optional `q`; no resume |
| getCandidate | GET | `/api/gpt/candidates/{candidate_id}` | READ | `include_resume` opt-in |
| listJobCandidates | GET | `/api/gpt/jobs/{job_id}/candidates` | READ | Candidates with evaluations |
| listEvaluations | GET | `/api/gpt/evaluations` | READ | Filter job/candidate |
| listJobEvaluations | GET | `/api/gpt/jobs/{job_id}/evaluations` | READ | |
| getEvaluation | GET | `/api/gpt/evaluations/{evaluation_id}` | READ | `include_items` opt-in |
| getJobCandidateEvaluation | GET | `/api/gpt/jobs/{job_id}/evaluations/{candidate_id}` | READ | |
| evaluateCandidate | POST | `/api/gpt/evaluations` | WRITE | Async Task |
| prefillCompensationFromJob | GET | `/api/gpt/compensation/prefill/{job_id}` | READ | Job → research prefill |
| listCompensationHistory | GET | `/api/gpt/compensation/history` | READ | Cached research summaries |
| getCompensationHistoryItem | GET | `/api/gpt/compensation/history/{cache_key}` | READ | `include_observations` opt-in |
| researchCompensationAsync | POST | `/api/gpt/compensation/research/async` | WRITE-like | Preferred; poll getTask |
| researchCompensation | POST | `/api/gpt/compensation/research` | WRITE-like | Sync; timeout risk |
| getTask | GET | `/api/gpt/tasks/{task_id}` | READ | Poll async work (score + compensation) |

## Comparison

| Desired | Status |
|---------|--------|
| compareCandidates endpoint | **NOT_IMPLEMENTED** — compare by fetching evaluations individually |

## Not exposed (by design)

| Capability | Status | Reason |
|------------|--------|--------|
| HTML UI routes (`GET /jobs`, `/compensation`, etc.) | Not in Actions | Return HTML, not JSON |
| Form `POST /jobs`, `POST /candidates` | Not in Actions | Multipart/form UI flows |
| Unauthenticated `/api/v1/compensation/*` | Not in Actions | UI/local JSON; GPT uses `/api/gpt/compensation/*` with same auth as other GPT Actions |
| Delete job/candidate/evaluation | **NOT_IMPLEMENTED** | No delete API |
| Sync evaluate (wait for score in one call) | **NOT_IMPLEMENTED** | Async + poll pattern |
| Create job / create candidate via JSON | **NOT_IMPLEMENTED** | Still form/async UI; propose later |
| OAuth per-user auth | **NOT_IMPLEMENTED** | API key for private/internal first |

## Compensation notes

- Prefer **async** research + `getTask` (mirrors UI). Sync is available but ChatGPT Action HTTP timeouts often fail on cold research.
- Prefer **job-linked** flow: `prefillCompensationFromJob` → adjust fields if needed → `researchCompensationAsync`.
- Free-form research is allowed when the user supplies profile/skills/seniority/location/contract without a job id.
- Auth: GPT compensation routes require `PROFESSIONAL_PROFILE_API_KEY` when configured (same as other `/api/gpt/*`). HTML `/compensation` and `/api/v1/compensation/*` stay open for local UI.

## Recommended future contracts

### POST `/api/gpt/jobs` (JSON) — NOT_IMPLEMENTED

Create/update job + optional analyse. Return Task or JobDetail.

### POST `/api/gpt/candidates` (JSON) — NOT_IMPLEMENTED

Ingest `resume_text` JSON body (no multipart). Return Task or CandidateDetail.

### POST `/api/gpt/evaluations/{id}/reprocess` — NOT_IMPLEMENTED

Alias of evaluate with explicit reprocess semantics (today: POST `/api/gpt/evaluations`).

### GET `/api/gpt/jobs/{job_id}/compare?candidate_ids=` — NOT_IMPLEMENTED

Optional convenience; not required if GPT composes from getEvaluation.
