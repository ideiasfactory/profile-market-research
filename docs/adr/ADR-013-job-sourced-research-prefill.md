# ADR-013 — Job-Sourced Research Prefill vs Free-Form

Decision: compensation research accepts free-form requests and optionally starts from an open job. Job mapping lives in `app.compensation.services.job_prefill` and is exposed by `GET /api/v1/compensation/prefill/{job_id}` and `/compensation?job_id=...`. Prefill sets profile, skills, seniority, allocation, contract and location; it does not invent salary observations.

Reason: researching against a real vacancy reduces form friction while keeping the compensation pipeline independent of job storage.
