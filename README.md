# Professional Profile Analyser

MVP leve para cadastrar vagas, currículos e gerar score de aderência de candidatos a oportunidades de tecnologia.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Acesse `http://127.0.0.1:8000`.

## LLM local

Por padrão o sistema chama o Ollama em `http://gpu-server-01:11434` usando o modelo `qwen2.5:14b`.
Se a LLM não responder, o sistema usa uma heurística local simples para permitir testar o fluxo completo.

No servidor do Ollama:

```bash
ollama pull qwen2.5:14b
ollama serve
```

Para sobrescrever a configuração:

```bash
export LOCAL_LLM_URL=http://gpu-server-01:11434
export LOCAL_LLM_MODEL=qwen2.5:14b
export LOCAL_LLM_TIMEOUT=90
export SCORING_MODEL=v2   # ou v1 para média ponderada flat
uvicorn app.main:app --reload
```

## Scoring model

- `SCORING_MODEL=v1` — média ponderada flat das skills (legado).
- `SCORING_MODEL=v2` (padrão) — score hierárquico: Core Technical, Role Fit, Context Fit, Behavioral, Differentials.
- Avaliações antigas **não** são recalculadas automaticamente; use “Gerar / reprocessar score” na UI.
- Soft skills sem evidência usam `score: null` + `needs_validation` e saem do denominador (v2).

## Testes

```bash
python -m unittest discover -s tests -v
```

## Dados

Os dados ficam em JSON dentro de `data/`:

- `data/domains.json` — domínios de perfil e senioridade
- `data/business_settings.json` — catálogo editável de parâmetros de negócio (impostos/margem são exemplos; qualquer chave)
- `data/jobs.json` — vagas (ainda monolítico; inclui `ideal_candidate_context` e analysis v2)
- `data/candidates.json` — índice leve de candidatos (sem `resume_text`)
- `data/candidates/{id}_{slug}_profile.json` — currículo completo de cada candidato
- `data/scores.json` — índice leve de scores
- `data/scores/{job_id}_{candidate_id}_{slug}_score.json` — detalhe completo de cada score

Na primeira carga, entradas monolíticas antigas em `candidates.json` / `scores.json` são migradas automaticamente para arquivos individuais (idempotente).

## Parâmetros de negócio

UI: `http://127.0.0.1:8000/settings` (abas **Parâmetros de negócio** e **Parâmetros de Sistema**).

- Catálogo genérico (CRUD): chave, rótulo, valor, tipo, categoria, descrição, flag “embutir em prompts”.
- Persistência: `data/business_settings.json` (`app/business_settings.py`).
- API: `GET/PUT /api/v1/settings/business`, `POST/DELETE .../parameters`.
- Chaves `clt_to_pj_factor` e `work_hours_month` alimentam a normalização de Compensation (fallback: `.env`).

Nos prompts (`prompts/`), use `{business_context}` ou `{<chave>}` — injetados por `load_prompt` quando `inject_in_prompts` está ativo (ADR-017, ADR-018).

### Parâmetros de Sistema e APIs Externas

- Aba **Parâmetros de Sistema** (`/settings?tab=sistema`): API keys e URLs (Tavily, Firecrawl, Ollama, API key do PPA). Persistência local em `data/system_settings.json` (gitignored); `.env` continua como fallback.
- Tela **APIs Externas** (`/external-apis`): plano, créditos usados/restantes e reset do ciclo via APIs oficiais:
  - Tavily `GET /usage` (reset documentado no 1º dia do mês)
  - Firecrawl `GET /v1/team/credit-usage` (período de billing na resposta)

## Prompts

Os prompts da LLM ficam externalizados em `prompts/` (fora do código da aplicação):

- `prompts/analyse_job.system.txt` / `analyse_job.user.txt`
- `prompts/extract_candidate.system.txt` / `extract_candidate.user.txt`
- `prompts/score_skills.system.txt` / `score_skills.user.txt`
- `prompts/score_fit.system.txt` / `score_fit.user.txt`
- `prompts/score_narrative.system.txt` / `score_narrative.user.txt`
- `prompts/score_candidate.system.txt` / `score_candidate.user.txt` (legado)

Edite esses arquivos para ajustar o comportamento da análise sem alterar o código Python. Parâmetros de negócio habilitados entram automaticamente via placeholders (ver seção acima).

## Escopo do MVP

- Cadastro, consulta e edição de domínios de perfil e senioridade.
- Catálogo editável de parâmetros de negócio (UI `/settings` + API), com injeção opcional nos prompts.
- Cadastro, consulta e edição de vagas (com `ideal_candidate_context` e tiers Must-have/Core/Supporting/Differentials).
- Job description em texto livre ou Markdown.
- Currículo via PDF, link de perfil no LinkedIn ou texto colado.
- Extração básica de nome, cidade e cargo.
- Análise da vaga com job understanding v2 + compatibilidade hard/soft/desired.
- Score candidato-vaga v1 (flat) ou v2 (composto), com evidência estruturada e explainability.
- Resumo do perfil do candidato e veredito gerados junto com o score.
- JSON API `/api/gpt` dedicada ao Custom GPT Actions (jobs, candidates, evaluations, compensation).
- Pacote de configuração do Custom GPT em `llm-tools/custom-gpt/` (Git = source of truth dos artefatos).
- Integração Open WebUI (tools OpenAPI + tool Python + system prompt + compose) em `llm-tools/tool-openwebui/`.

### API GPT (`/api/gpt`)

Endpoints de leitura para vagas, candidatos e avaliações, mais `POST /api/gpt/evaluations` (assíncrono), compensation research (`/async`, `/wait`, sync) e `GET /api/gpt/tasks/{task_id}`.  
Autenticação opcional via `PROFESSIONAL_PROFILE_API_KEY` (Bearer ou `X-API-Key`).  
Detalhes e OpenAPI para o GPT: `llm-tools/custom-gpt/actions/`.

### Open WebUI

Frontend conversacional self-hosted (Ollama em `gpu-server-01:11434`) com tools apontando para `/api/gpt/*`.  
Guia, OpenAPI slim, system prompt e docker-compose: [`llm-tools/tool-openwebui/`](llm-tools/tool-openwebui/).  
Política de cache na conversa: `force_refresh` padrão **false** (só true se o usuário pedir para ignorar o cache).

### Entrada de currículo

Prioridade de origem: **arquivo (PDF/TXT/MD) → texto colado → LinkedIn**.

O LinkedIn costuma bloquear leitura automática (auth wall). Quando isso acontecer, o sistema pede PDF ou texto exportado do perfil.

## v1 — Compensation Intelligence API

Pesquisa auditável de remuneração de mercado (evidência + URL; LLM extrai, Python calcula).

### Como rodar

1. Copie `.env.example` → `.env` e preencha `TAVILY_API_KEY` (e opcionalmente `FIRECRAWL_API_KEY`).
2. Suba a API (`uvicorn app.main:app --reload`). O processo carrega `.env` automaticamente via `app/env_loader.py` sem sobrescrever variáveis já exportadas.
3. Abra `http://127.0.0.1:8000/compensation`.

### Endpoints

| Método | Path | Uso |
| --- | --- | --- |
| `POST` | `/api/v1/compensation/research` | Pesquisa síncrona (scripts/smoke) |
| `POST` | `/api/v1/compensation/research/async` | Pesquisa async (UI); poll em `/api/tasks/{id}` |
| `GET` | `/api/v1/compensation/history` | Lista pesquisas em cache |
| `GET` | `/api/v1/compensation/history/{cache_key}` | Reabre resultado cacheado |
| `GET` | `/api/v1/compensation/prefill/{job_id}` | Prefill a partir de uma vaga |
| `GET` | `/health`, `/health/llm`, `/health/providers` | Liveness + Ollama + providers/API keys |

### UI

- `/compensation` — formulário livre, histórico (`data/compensation_cache`), overlay de progresso e resultados.
- `/compensation?job_id=...` — mesmo fluxo pré-preenchido a partir da vaga (também há botão no detalhe da vaga).
- TTL do cache: parâmetro `cache_ttl_days` (UI `/settings`, padrão **30** dias). Consultas reutilizam o cache enquanto a idade do arquivo for ≤ TTL; acima disso o cache é invalidado e a research roda de novo (`force_refresh=true` ignora o cache imediatamente).

Exemplo síncrono:

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
    "providers": {
      "search_engines": ["tavily"],
      "crawlers": ["glassdoor", "indeed", "vagas", "generic"]
    },
    "force_refresh": false
  }'
```

Configuração: `config/providers.yaml`, `config/source_registry.yaml`, `.env.example`.

Persistência: `data/research_history.jsonl`, `data/observations.jsonl`, `data/compensation_cache/`.

Docs: `docs/architecture.md`, `docs/api-contract.md`, `docs/adr/` (ADR-001 … ADR-020).
