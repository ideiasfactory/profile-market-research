# Compensation Intelligence API v1

## Objetivo

Adicionar ao Professional Profile Analyser uma API MVP de pesquisa de remuneração de mercado para perfis de tecnologia, mantendo a v0 intacta.

## Fluxo end-to-end

```text
Client (UI /compensation ou API)
  -> FastAPI (app/api/compensation.py)
       sync:  POST /api/v1/compensation/research
       async: POST /api/v1/compensation/research/async
              -> task_store + GET /api/tasks/{id}
  -> CompensationResearchOrchestrator
       -> cache lookup (data/compensation_cache/, TTL)
       -> ProfileNormalizer (Ollama + fallback heurístico)
       -> QueryPlanner
       -> ProviderRegistry
            -> SearchEngines (Tavily / Firecrawl)
            -> Crawlers (Glassdoor, Indeed, Vagas, Catho*, Generic)
       -> LLM Extractor (+ regex fallback)
       -> Deduplication
       -> Quality filters (senioridade, período, bounds)
       -> Normalization (CLT/PJ, período → unidade alvo)
       -> Absolute plausibility pós-normalização
       -> Statistics + IQR outliers (N >= 5)
       -> Confidence Engine
       -> Persistência JSONL + cache JSON
```

\* Catho existe como adapter; desabilitado por padrão em `ENABLED_CRAWLERS`.

## UI

- Página: `GET /compensation` (`app/templates/compensation.html` + `app/static/compensation.js`).
- Modo livre: formulário com providers, skills, localidade e contrato.
- Modo vaga: `GET /compensation?job_id=...` (botão em detalhe da vaga) pré-preenche via `job_prefill`.
- Pesquisa assíncrona com overlay de progresso (poll em `/api/tasks/{id}`).
- Histórico: lista pesquisas em `data/compensation_cache` (`GET /api/v1/compensation/history`).
- Reabertura: `GET /api/v1/compensation/history/{cache_key}` ou `?cache_key=...`.
- Parâmetros de negócio: `GET /settings` (catálogo genérico; ver seção abaixo).

## Parâmetros de negócio

Catálogo editável (não é schema fixo de impostos/margem):

```text
UI /settings  ou  API /api/v1/settings/business
  -> app/business_settings.py
  -> data/business_settings.json
  -> values[key] usado por CompensationSettings (clt_to_pj_factor, work_hours_month)
  -> load_prompt() injeta {key} e {business_context} quando inject_in_prompts=true
```

| Área | Caminho |
| --- | --- |
| Domínio + store | `app/business_settings.py` |
| UI | `app/templates/settings.html` |
| Rotas HTML/API | `app/main.py` (`/settings`, `/api/v1/settings/business*`) |
| Injeção em prompts | `app/prompts.py` → `load_prompt` |

ADRs: ADR-017 (catálogo), ADR-018 (prompts).

## Princípios

- Nenhum salário entra no cálculo sem evidência textual.
- Nenhuma evidência é aceita sem URL.
- LLM extrai estrutura; Python calcula remuneração, percentis e confidence.
- Search engines e crawlers são selecionados exclusivamente pelo `ProviderRegistry`.
- Crawlers não tentam burlar CAPTCHA, autenticação, paywall ou bloqueio explícito.
- Filtros de qualidade (senioridade / plausibilidade) rodam antes das estatísticas de mercado.
- Logs estruturados JSON incluem `research_id` (`app/compensation/logging_utils.py`).

## Módulos principais

| Área | Caminho |
| --- | --- |
| API + página | `app/api/compensation.py` |
| Orquestrador | `app/compensation/services/orchestrator.py` |
| Qualidade | `app/compensation/services/quality.py` |
| Estatísticas | `app/compensation/services/statistics.py` |
| Prefill de vaga | `app/compensation/services/job_prefill.py` |
| Histórico/cache UI | `app/compensation/services/history.py` |
| Registry | `app/compensation/registry.py` |
| Env startup | `app/env_loader.py` (chamado em `app/main.py`) |
| Tasks async | `app/tasks.py` |
| Parâmetros de negócio | `app/business_settings.py`, `data/business_settings.json` |
| Prompts + injeção | `app/prompts.py`, `prompts/` |
| Config | `config/providers.yaml`, `config/source_registry.yaml`, `.env.example` |
| Pacotes conversacionais | `llm-tools/custom-gpt/`, `llm-tools/tool-openwebui/` (ADR-016, ADR-019) |

## Persistência

- `data/research_history.jsonl` — audit trail de pesquisas.
- `data/observations.jsonl` — observações append-only.
- `data/compensation_cache/{cache_key}.json` — resposta completa + fonte do histórico da UI.
- `data/business_settings.json` — catálogo de parâmetros de negócio (UI `/settings`).
- Cache key determinística da consulta; TTL via parâmetro de negócio `cache_ttl_days` (padrão 30; fallback `.env` `CACHE_TTL_DAYS`).

## Observabilidade

- `LOG_LEVEL` controla o nível global.
- Eventos de pesquisa: `research_started`, `research_progress`, `search_*`, `crawl_*`, `observations_*`, `research_completed` / `research_failed`.
- Health:
  - `GET /health` — liveness.
  - `GET /health/llm` — reachability do Ollama + modelo.
  - `GET /health/providers` — health dos search engines, crawlers habilitados e status `set`/`missing` das API keys.

## Deploy

- API no IHL (mesmo processo FastAPI da v0).
- Na subida, `load_app_env()` carrega `.env` sem sobrescrever variáveis já exportadas.
- Ollama em `http://gpu-server-01:11434`.
- Modelo default: `qwen2.5:14b`.
- Keys externas: `TAVILY_API_KEY`, `FIRECRAWL_API_KEY` (opcional).

## ADRs relevantes

Índice completo: [`docs/adr/README.md`](adr/README.md).

- ADR-001 — Separação LLM × compensation engine
- ADR-002–004 — Abstração e registry de search/crawlers
- ADR-005–006 — Glassdoor + Playwright fallback
- ADR-007 — Ollama em gpu-server-01
- ADR-008 — Extração baseada em evidência
- ADR-009 — JSONL para persistência MVP
- ADR-010 — Logs estruturados por `research_id`
- ADR-011 — Pesquisa async com progresso
- ADR-012 — Filtros de qualidade antes das stats
- ADR-013 — Prefill a partir de vaga vs free-form
- ADR-014 — Load `.env` no startup
- ADR-015 — Cache como histórico da UI
- ADR-016 — Open WebUI como frontend conversacional + cache-default
- ADR-017 — Catálogo editável de parâmetros de negócio
- ADR-018 — Injeção de parâmetros de negócio nos prompts
- ADR-019 — Pacotes conversacionais consolidados em `llm-tools/`
- ADR-020 — Dashboard de uso de APIs externas + aba Parâmetros de Sistema

## Roadmap Pós-MVP

- Parsers mais profundos por fonte (Catho, Robert Half, Michael Page).
- Guias salariais PDF.
- Rate limiting por domínio.
- Persistência PostgreSQL quando JSONL/cache deixar de escalar.
- Integração Solides / base interna Aggrandize.
- Skill Premium Engine e Location Premium Engine.
- Modelo proprietário de Compensation Intelligence.
- Docker/IHL com Playwright/Chromium pré-instalado.
