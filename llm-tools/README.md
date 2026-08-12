# LLM tools / conversational packages

Artefatos para frontends conversacionais do Professional Profile Analyser (PPA).

| Pasta | Uso |
|-------|-----|
| [`tool-openwebui/`](./tool-openwebui/) | Open WebUI — OpenAPI Global Tool Server (preferido), tool Python (fallback), system prompt, compose |
| [`custom-gpt/`](./custom-gpt/) | ChatGPT Custom GPT — Instructions, Knowledge, Actions OpenAPI |

Paths legados (só redirects): `integrations/open-webui/` → `tool-openwebui/`; `app-custom-gpt/` → `custom-gpt/`.

Decisões: [ADR-016](../docs/adr/ADR-016-open-webui-conversational-frontend.md) (Open WebUI + cache-default), [ADR-019](../docs/adr/ADR-019-consolidate-conversational-packages-under-llm-tools.md) (layout `llm-tools/`).

A API consumida pelos tools é `/api/gpt/*` no app FastAPI (`app/gpt.py`), não os artefatos desta pasta.
