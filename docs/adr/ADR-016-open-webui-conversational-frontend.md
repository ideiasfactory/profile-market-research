# ADR-016 — Open WebUI as Conversational Frontend + Cache-Default for Compensation

## Status

Accepted (post v0.2.0)

## Context

v0.2.0 shipped a Custom GPT package (`llm-tools/custom-gpt/`, formerly `app-custom-gpt/`) calling `/api/gpt/*`. Labs that already run Ollama on `gpu-server-01` also want a **self-hosted** conversational UI. Open WebUI can attach OpenAPI tools to local models, but async Task + poll loops are awkward in some tool runtimes.

Compensation research is expensive (search + crawl). Users and models often over-use `force_refresh=true`. The HTML UI may keep a “force refresh” checkbox checked for operator convenience; the **API schema** and **conversational** path must still default to cache.

## Decision

1. Treat **Open WebUI** as an optional conversational frontend alongside Custom GPT and the HTML UI. Artifacts live under `llm-tools/tool-openwebui/` (slim OpenAPI, optional Python Workspace tool, system prompt, compose overlay).
2. Tools must call **`/api/gpt/*`** (API-key aware), not unauthenticated `/api/v1/compensation/*`.
3. **Cache policy for conversational clients:** `force_refresh` defaults to **`false`**. Set `true` only on explicit user instruction to ignore cache / force a new research.
4. Add GPT-facing helper **`POST /api/gpt/compensation/research/wait`** that runs research and returns the final payload in one call (UX for Open WebUI). Do not change `/api/v1/*` UI routes or the UI form’s checkbox default.

## Consequences

- Operators can run Open WebUI + Ollama without ChatGPT Actions, reusing the same GPT API surface.
- Models are steered (prompt + OpenAPI descriptions) away from unnecessary cache busting.
- Sync/`wait` calls may hit client HTTP timeouts on cold research; async+poll remains available when the tool layer supports it.
- Custom GPT OpenAPI remains the fuller Actions catalog; the Open WebUI slim spec is a deliberate subset.
- Repository layout for these packages is fixed in ADR-019 (`llm-tools/`).
