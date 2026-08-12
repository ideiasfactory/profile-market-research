# ADR-011 — Async Research with Progress Feedback

Decision: the UI and long-running clients start research via `POST /api/v1/compensation/research/async`, reuse the shared in-memory `task_store`, and poll `GET /api/tasks/{task_id}`. The orchestrator reports progress through an `on_progress` callback. Synchronous `POST /api/v1/compensation/research` remains available for scripts and smoke tests.

Reason: a full search/crawl/extract cycle often exceeds interactive HTTP expectations; progress feedback keeps the UI usable without introducing a separate job queue for MVP.
