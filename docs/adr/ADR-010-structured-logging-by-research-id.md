# ADR-010 — Structured Logging by research_id

Decision: compensation research emits JSON log events via `app.compensation.logging_utils`, binding every event to the active `research_id` through a `ContextVar`.

Reason: long-running multi-provider research must be correlatable across search, crawl, extraction and stats without relying on request timestamps alone.
