# Handoff — v1 Compensation Intelligence API

Data: 2026-08-12  
Projeto: `professional_profile_analyser`  
Repositório remoto: `https://github.com/ideiasfactory/profile-market-research.git`  
Objetivo deste handoff: permitir retomar a v1 em outra sessão/Cursor sem depender do histórico do chat.

## Contexto

A v0 do sistema já existia como aplicação FastAPI/Jinja para:

- cadastro de domínios;
- cadastro de vagas;
- cadastro de currículos;
- análise de perfil/candidato;
- score candidato-vaga;
- persistência local em JSON.

A v1 adiciona uma API de `Compensation Intelligence` para pesquisar remuneração de mercado com evidência, fontes e cálculo determinístico.

Princípio central:

```text
search/crawling + evidence + LLM extraction + Python compensation engine = market estimate
```

O LLM não calcula remuneração final. Ele só extrai observações estruturadas.

## Status Atual

Implementado e validado:

- endpoint principal `POST /api/v1/compensation/research`;
- pesquisa async `POST /api/v1/compensation/research/async` + poll `GET /api/tasks/{id}`;
- histórico `GET /api/v1/compensation/history` e `.../history/{cache_key}` (fonte: `data/compensation_cache`);
- prefill de vaga `GET /api/v1/compensation/prefill/{job_id}` e UI `/compensation?job_id=...`;
- health checks `/health`, `/health/llm`, `/health/providers` (inclui status de API keys);
- UI operacional em `/compensation` (formulário, histórico, progresso, resultados);
- catálogo de parâmetros de negócio em `/settings` + API `/api/v1/settings/business*` (ADR-017/018);
- load de `.env` no startup (`app/env_loader.py`);
- logs estruturados JSON por `research_id` (`app/compensation/logging_utils.py`);
- contratos Pydantic da v1;
- `ProviderRegistry` central;
- search adapters Tavily e Firecrawl;
- crawlers Glassdoor, Indeed, Vagas, Catho e Generic;
- crawling HTTP com fallback opcional para Playwright;
- fallback de snippet quando crawling falha/bloqueia;
- normalização de perfil via Ollama com fallback heurístico;
- query planner com queries genéricas e específicas por fonte;
- extração de salários via LLM com fallback regex;
- regra `no evidence = no observation`;
- filtros de qualidade (senioridade, período, bounds absolutos) antes das stats;
- normalização CLT mensal → PJ/h;
- normalização PJ mês → PJ/h;
- normalização anual → mensal;
- deduplicação de URLs e observações;
- cálculo de P25, mediana, média, P75, mínimo, máximo e faixa recomendada;
- outlier detection por IQR quando `N >= 5`;
- confidence engine;
- persistência JSONL/cache;
- pacotes conversacionais em `llm-tools/` (Custom GPT + Open WebUI; ADR-016/019);
- documentação e ADRs (ADR-001 … ADR-019; ver `docs/architecture.md`).

Validação executada:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Resultado: `25 tests OK`.

## Pontos De Entrada

API:

- `app/api/compensation.py`

Orquestrador:

- `app/compensation/services/orchestrator.py`

Schemas:

- `app/compensation/domain/schemas.py`

Registry:

- `app/compensation/registry.py`

Config:

- `config/providers.yaml`
- `config/source_registry.yaml`
- `.env.example`
- `data/business_settings.json` (parâmetros de negócio editáveis)

Docs:

- `docs/architecture.md` (fluxo atual, UI, async, qualidade, parâmetros de negócio, ADRs)
- `docs/api-contract.md` (sync/async, history, prefill, health, settings/business)
- `docs/adr/` (ADR-001 … ADR-019)
- `llm-tools/README.md` (Custom GPT + Open WebUI)

Testes v1:

- `tests/unit/test_compensation_engine.py`
- `tests/unit/test_business_settings.py`

## Contrato Principal

Endpoint:

```http
POST /api/v1/compensation/research
```

Exemplo:

```json
{
  "profile": "Arquiteto de Soluções Senior Cloud e Microserviços",
  "skills": ["Azure", "AKS", "Kubernetes", "Microservices"],
  "seniority": "senior",
  "allocation_model": "hybrid",
  "location": {"city": "Campinas", "state": "SP", "country": "BR"},
  "target_contract": "PJ",
  "providers": {
    "search_engines": ["tavily"],
    "crawlers": ["glassdoor", "indeed", "vagas", "generic"]
  },
  "force_refresh": false
}
```

Resposta esperada:

- `research_id`;
- perfil normalizado;
- estatísticas de mercado;
- sample size;
- providers usados;
- confidence;
- fontes;
- warnings;
- observações.

## Variáveis De Ambiente

Definidas em `.env.example`:

```bash
OLLAMA_BASE_URL=http://gpu-server-01:11434
OLLAMA_MODEL=qwen2.5:14b
SEARCH_ENGINES=tavily
ENABLED_CRAWLERS=glassdoor,indeed,vagas,generic
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
CLT_TO_PJ_FACTOR=1.50
WORK_HOURS_MONTH=168
MAX_PARALLEL_SEARCHES=4
MAX_PARALLEL_CRAWLS=5
CACHE_TTL_DAYS=30
HTTP_TIMEOUT_SECONDS=10
PLAYWRIGHT_TIMEOUT_SECONDS=20
RESEARCH_TIMEOUT_SECONDS=120
APP_API_KEY=
```

`CLT_TO_PJ_FACTOR`, `WORK_HOURS_MONTH` e `CACHE_TTL_DAYS` também existem como parâmetros editáveis em `data/business_settings.json` (UI `/settings`; chave `cache_ttl_days`, padrão **30** dias). O catálogo tem precedência quando as chaves estão presentes (ADR-017). Cache com idade maior que o TTL é invalidado e a research roda de novo.

Observação operacional:

- O Ollama deve rodar em `gpu-server-01:11434`.
- O modelo existente verificado anteriormente foi `qwen2.5:14b`.
- A porta do Ollama não deve ser exposta externamente.

## Como Rodar Localmente

```bash
cd /Users/flaviolopes/projects/lab/professional_profile_analyser
source .venv/bin/activate
uvicorn app.main:app --reload
```

Abrir:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/compensation
```

Smoke básico sem depender de API key externa:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/compensation/research \
  -H 'Content-Type: application/json' \
  -d '{
    "profile": "Arquiteto de Soluções Senior Cloud e Microserviços",
    "skills": ["Azure", "AKS", "Kubernetes", "Microservices"],
    "seniority": "senior",
    "allocation_model": "hybrid",
    "location": {"city": "Campinas", "state": "SP", "country": "BR"},
    "target_contract": "PJ",
    "providers": {"search_engines": [], "crawlers": ["generic"]},
    "force_refresh": true
  }'
```

Resultado esperado nesse smoke:

- HTTP 200;
- `sample.observations = 0`;
- `confidence.level = LOW`;
- warning informando ausência de observações com evidência salarial.

## Persistência

Arquivos da v1:

- `data/research_history.jsonl`
- `data/observations.jsonl`
- `data/compensation_cache/*.json`

O cache usa hash determinístico da consulta e TTL por `CACHE_TTL_DAYS`.

## Guardrails Importantes

Não alterar sem decisão explícita:

1. Nenhum salário sem evidência.
2. Nenhuma evidência sem URL.
3. LLM não calcula remuneração final.
4. Valores originais sempre preservados em `observed_salary`.
5. Normalização calculada em Python em `normalized_salary`.
6. Provider não deve ser hard-coded no orquestrador.
7. Crawler pode falhar sem falhar a pesquisa inteira.
8. Não burlar CAPTCHA, autenticação, paywall ou bloqueio explícito.
9. Evitar falsa precisão quando `N` é baixo.

## Arquitetura Implementada

Resumo canônico em `docs/architecture.md`. Fluxo:

```text
FastAPI (sync ou async + task_store)
  -> CompensationResearchOrchestrator
    -> ProfileNormalizer
    -> QueryPlanner
    -> ProviderRegistry
      -> TavilySearchEngine / FirecrawlSearchEngine
      -> GlassdoorCrawler / IndeedCrawler / VagasCrawler / GenericCrawler
    -> LLM Extractor
    -> Deduplication
    -> Quality filters
    -> Normalization
    -> Statistics (+ IQR)
    -> Confidence
    -> JSONL/cache persistence
```

## Limitações Conhecidas

- `TAVILY_API_KEY` e `FIRECRAWL_API_KEY` não estão configuradas no repo.
- Playwright está declarado em `pyproject.toml`, mas Chromium precisa ser instalado no ambiente:

```bash
playwright install chromium
```

- O crawler especializado ainda é MVP: ele limpa conteúdo e delega interpretação ao extractor; não há parser profundo específico por layout.
- `CathoCrawler` existe como adapter, mas vem desabilitado por padrão.
- `task_store` é in-memory (tasks somem no restart; adequado ao MVP).
- Rate limiting por domínio ainda usa limite global simples por semáforo; não há semáforo separado por domínio.
- Docker/IHL ainda precisa ser fechado para produção.

## Próximos Passos Recomendados

Ordem pragmática:

1. Configurar `TAVILY_API_KEY` no ambiente.
2. Rodar pesquisa real (UI async ou sync) com `providers.search_engines=["tavily"]`.
3. Validar queries geradas para o caso Campinas/Azure/AKS.
4. Revisar documentos retornados por Glassdoor/Indeed/Vagas.
5. Melhorar parsers por fonte apenas onde houver evidência de ganho.
6. Adicionar rate limiting por domínio.
7. Preparar Docker com Playwright/Chromium.
8. Fazer deploy no IHL.
9. Criar testes de integração com mocks de Tavily/crawlers.

## Definition Of Done Da v1

Para considerar v1 operacional em ambiente real:

- API rodando no IHL;
- `/health`, `/health/llm`, `/health/providers` OK;
- Ollama acessível em `gpu-server-01`;
- `TAVILY_API_KEY` configurada;
- ao menos uma pesquisa real retorna fontes/URLs;
- nenhuma observation é criada sem evidência explícita;
- estatísticas e confidence retornam coerentes com amostra;
- testes locais continuam verdes.

## Comandos Úteis

Testes:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Compilação:

```bash
.venv/bin/python -m compileall app
```

Health:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/llm
curl http://127.0.0.1:8000/health/providers
```

Git remoto:

```bash
git remote -v
```

Estado atual do remoto configurado:

```text
origin -> https://github.com/ideiasfactory/profile-market-research.git
```
