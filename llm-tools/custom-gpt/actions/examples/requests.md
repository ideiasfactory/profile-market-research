# Action Request Examples

custom_gpt_version: 0.2.0  
actions_version: 1.1

Assume base URL `https://YOUR_PPA_HOST` and header `Authorization: Bearer ${PROFESSIONAL_PROFILE_API_KEY}` when auth is enabled.

## listJobs

```http
GET /api/gpt/jobs?q=CPFL
```

## getJob

```http
GET /api/gpt/jobs/671bb12e8d6c
```

## listCandidates

```http
GET /api/gpt/candidates?q=Bruno
```

## getCandidate (metadata only)

```http
GET /api/gpt/candidates/e475d1052f49
```

## getCandidate (with resume)

```http
GET /api/gpt/candidates/e475d1052f49?include_resume=true
```

## listJobCandidates

```http
GET /api/gpt/jobs/671bb12e8d6c/candidates
```

## listJobEvaluations

```http
GET /api/gpt/jobs/671bb12e8d6c/evaluations
```

## getEvaluation

```http
GET /api/gpt/evaluations/671bb12e8d6c_e475d1052f49?include_items=true
```

## getJobCandidateEvaluation

```http
GET /api/gpt/jobs/671bb12e8d6c/evaluations/e475d1052f49
```

## evaluateCandidate (WRITE)

```http
POST /api/gpt/evaluations
Content-Type: application/json

{
  "job_id": "671bb12e8d6c",
  "candidate_id": "e475d1052f49",
  "scoring_model": "v2"
}
```

## getTask

```http
GET /api/gpt/tasks/{task_id}
```

## prefillCompensationFromJob

```http
GET /api/gpt/compensation/prefill/671bb12e8d6c
```

## listCompensationHistory

```http
GET /api/gpt/compensation/history
```

## getCompensationHistoryItem (compact)

```http
GET /api/gpt/compensation/history/81d56a04f156896175839424213a0971
```

## getCompensationHistoryItem (with observations)

```http
GET /api/gpt/compensation/history/81d56a04f156896175839424213a0971?include_observations=true
```

## researchCompensationAsync (preferred WRITE-like)

```http
POST /api/gpt/compensation/research/async
Content-Type: application/json

{
  "profile": "Arquiteto de Soluções Senior Cloud e Microserviços",
  "skills": ["Azure", "AKS", "Kubernetes", "Microservices"],
  "seniority": "senior",
  "allocation_model": "hybrid",
  "location": { "city": "Campinas", "state": "SP", "country": "BR" },
  "target_contract": "PJ",
  "force_refresh": false,
  "source_job_id": "671bb12e8d6c"
}
```

## researchCompensation (sync — timeout risk)

```http
POST /api/gpt/compensation/research?include_observations=false
Content-Type: application/json

{
  "profile": "Arquiteto de Soluções Senior Cloud",
  "skills": ["Azure", "Kubernetes"],
  "seniority": "senior",
  "allocation_model": "remote",
  "location": { "city": "São Paulo", "state": "SP", "country": "BR" },
  "target_contract": "PJ"
}
```
