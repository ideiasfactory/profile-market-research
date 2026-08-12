# ADR-019 — Consolidate Conversational Packages under `llm-tools/`

## Status

Accepted

## Context

Artefatos do Custom GPT estavam em `app-custom-gpt/`. A integração Open WebUI surgiu em paralelo (`integrations/open-webui/`). Manter pastas na raiz com nomes distintos dificultava descoberta (“onde está o pacote conversacional?”) e misturava app runtime (`app/`) com packaging de clientes LLM.

## Decision

1. Agrupar pacotes conversacionais sob **`llm-tools/`**:
   - `llm-tools/custom-gpt/` — Instructions, Knowledge, Actions OpenAPI, checklists
   - `llm-tools/tool-openwebui/` — OpenAPI slim, tool Python, system prompt, compose
2. Deixar stubs de redirect em `app-custom-gpt/README.md` e `integrations/open-webui/README.md` apontando para os novos caminhos.
3. A API de produto permanece em `app/` (`/api/gpt/*`); `llm-tools/` não contém runtime da API, só artefatos e glue dos clientes.

## Consequences

- Um único ponto de entrada documental (`llm-tools/README.md`) para frontends conversacionais.
- Paths antigos não quebram bookmarks de operadores (README redirect).
- ADR-016 (Open WebUI + cache-default) continua válido; este ADR fixa apenas a **organização do repositório**.
