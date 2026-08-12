# ADR-020 — External API Usage Dashboard + System Settings Tab

## Status

Accepted

## Context

Operators need visibility into contracted plans and credit consumption for Tavily and Firecrawl, and a safe place in the UI to edit API keys and service base URLs without mixing them into free-form business parameters (which can be injected into LLM prompts).

Both vendors expose usage APIs:

- Tavily: `GET https://api.tavily.com/usage` (Bearer) → key + account plan usage/limits. Credits reset on the **1st of each month** (vendor FAQ; not always a field in the payload).
- Firecrawl: `GET /v1/team/credit-usage` (Bearer; v2 fallback) → remaining/plan credits and billing period start/end.

## Decision

1. Add UI **APIs Externas** (`/external-apis`) that calls those endpoints live and shows plan, used/remaining, period/reset, and breakdown when available. The same screen also surfaces **OpenAI** usage from local metering (`data/llm_usage.jsonl` / `summarize_usage`) — tokens and estimated USD cost — not the Billing Admin API.
2. Split `/settings` into tabs:
   - **Parâmetros de negócio** — existing editable catalog (prompt-injectable).
   - **Parâmetros de Sistema** — fixed catalog of keys/URLs (`app/system_settings.py`), secrets masked, blank secret keeps previous value.
3. Persist system overrides in `data/system_settings.json` (**gitignored**); resolve `store → env → default` and apply overrides into `os.environ` at startup and on save so search adapters pick them up immediately.
4. Do **not** inject system secrets into prompts.

## Consequences

- Ops can audit credit burn without leaving the app.
- Business and system concerns stay separated (security + clearer UX).
- Live usage depends on valid keys and vendor API availability; missing keys show an actionable empty state linking to system settings.
