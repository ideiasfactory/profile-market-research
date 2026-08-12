# API Contract — Compensation Intelligence v1 (+ settings)

Contrato da API de Compensation e do catálogo de parâmetros de negócio.

## `POST /api/v1/compensation/research`

Synchronous research. Prefer the async endpoint for UI / long runs.

### Request

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
  "force_refresh": false,
  "source_job_id": null
}
```

### Response

```json
{
  "research_id": "...",
  "profile": {
    "normalized_role": "Cloud Solution Architect",
    "role_family": "solution_architecture",
    "seniority": "senior"
  },
  "market": {
    "currency": "BRL",
    "unit": "hour",
    "contract_type": "PJ",
    "minimum": 95,
    "p25": 100,
    "median": 110,
    "mean": 112,
    "p75": 120,
    "maximum": 135,
    "monthly_equivalent": 18816,
    "recommended_range": {"min": 100, "max": 120}
  },
  "sample": {"observations": 12, "sources": 6},
  "providers": {
    "search_engines_used": ["tavily"],
    "crawlers_used": ["glassdoor", "indeed", "vagas"]
  },
  "confidence": {"score": 0.81, "level": "HIGH"},
  "sources": [{"name": "glassdoor", "url": "...", "observations": 3}],
  "warnings": [],
  "observations": [],
  "created_at": "2026-08-12T00:00:00+00:00"
}
```

## `POST /api/v1/compensation/research/async`

Starts research in a background task and returns immediately.

### Response

```json
{
  "task_id": "...",
  "kind": "compensation_research",
  "status": "queued",
  "progress": 0,
  "message": "Aguardando processamento",
  "redirect_url": null,
  "error": null,
  "result": null,
  "created_at": "..."
}
```

Poll progress and final payload:

```http
GET /api/tasks/{task_id}
```

When `status` is `completed`, `result` holds the same body as the sync research response. On failure, `status` is `failed` and `error` is set.

## History

### `GET /api/v1/compensation/history`

Lists cached researches from `data/compensation_cache/*.json` (newest first).

```json
{
  "items": [
    {
      "cache_key": "...",
      "research_id": "...",
      "normalized_role": "Cloud Solution Architect",
      "seniority": "senior",
      "contract_type": "PJ",
      "unit": "hour",
      "median": 110,
      "recommended_min": 100,
      "recommended_max": 120,
      "observations": 12,
      "sources": 6,
      "confidence_level": "HIGH",
      "confidence_score": 0.81,
      "search_engines_used": ["tavily"],
      "crawlers_used": ["glassdoor"],
      "created_at": "...",
      "updated_at": 0
    }
  ]
}
```

### `GET /api/v1/compensation/history/{cache_key}`

Returns the full cached research payload, or `404` if missing.

## Job prefill

### `GET /api/v1/compensation/prefill/{job_id}`

Maps an open job to a compensation form payload (`profile`, `skills`, `seniority`, `allocation_model`, `target_contract`, `location`, `source_job_id`, optional job compensation hints). Returns `404` if the job does not exist.

UI equivalent: `GET /compensation?job_id={job_id}`.

## UI

- `GET /compensation` — form, history sidebar, progress overlay, results.
- Optional query params: `job_id`, `cache_key`.

## Health

### `GET /health`

```json
{"status": "healthy"}
```

### `GET /health/llm`

```json
{
  "status": "healthy",
  "base_url": "http://gpu-server-01:11434",
  "model": "qwen2.5:14b"
}
```

Unhealthy responses include `error`.

### `GET /health/providers`

```json
{
  "search_engines": {"tavily": "healthy"},
  "crawlers": {"glassdoor": "enabled", "indeed": "enabled", "vagas": "enabled", "generic": "enabled"},
  "configured_search_engines": ["tavily"],
  "api_keys": {"tavily": "set", "firecrawl": "missing"}
}
```

`api_keys` values are `set` or `missing` (never the secret itself). Search engine values come from each adapter’s `health()` (e.g. `healthy`, `missing_api_key`).

## Business parameters

Editable catalog (generic keys; tax/margin seeds are examples only). See ADR-017 / ADR-018.

### `GET /api/v1/settings/business`

```json
{
  "parameters": [
    {
      "id": "param_target_margin_pct",
      "key": "target_margin_pct",
      "label": "Margem alvo (%)",
      "value": 25.0,
      "value_type": "percent",
      "category": "pricing",
      "description": "...",
      "inject_in_prompts": true
    }
  ],
  "values": {"target_margin_pct": 25.0, "clt_to_pj_factor": 1.5},
  "updated_at": "2026-08-12T15:00:00+00:00"
}
```

### `PUT /api/v1/settings/business`

Replace the full catalog. Body: `{ "parameters": [ ... ] }`. Returns the normalized settings (including `values`).

### `POST /api/v1/settings/business/parameters`

Upsert one parameter (by `id` or `key`).

### `DELETE /api/v1/settings/business/parameters/{item_id}`

Delete by parameter `id` (or `key` if it matches).

### UI

- `GET /settings` — list/edit/create/delete parameters; preview of `{business_context}` for prompts.
