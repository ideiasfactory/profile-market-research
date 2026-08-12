# ADR-015 — Compensation Cache as UI History Source

Decision: the `/compensation` UI history and `GET /api/v1/compensation/history` read completed researches from `data/compensation_cache/*.json` via `app.compensation.services.history`. JSONL files (`research_history.jsonl`, `observations.jsonl`) remain append-only audit trails; the cache is the interactive history source of truth for the MVP UI.

Reason: cached response JSON already contains the full research payload needed to reopen results without parsing append-only JSONL.
