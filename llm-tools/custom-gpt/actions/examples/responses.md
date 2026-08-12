# Action Response Examples

custom_gpt_version: 0.2.0  
actions_version: 1.1

Illustrative shapes (values are examples, not golden scores / salaries).

## listJobs 200

```json
{
  "count": 1,
  "jobs": [
    {
      "id": "671bb12e8d6c",
      "title": "Arquiteto OIC - CPFL",
      "description": "Vaga para Arquiteto OIC",
      "profile": "Arquiteto",
      "seniority": "Especialista",
      "work_location": "Híbrido",
      "has_analysis": true
    }
  ]
}
```

## getCandidate 200 (default)

```json
{
  "id": "e475d1052f49",
  "name": "Bruno Libanio",
  "city": "Campinas, São Paulo, Brasil",
  "reported_role": "Tech Lead | Team Lead | Arquiteto de Soluções",
  "source_type": "pdf",
  "resume_available": true,
  "resume_length": 12000
}
```

## getEvaluation 200 (compact)

```json
{
  "evaluation_id": "671bb12e8d6c_e475d1052f49",
  "candidate": { "id": "e475d1052f49", "name": "Bruno Libanio" },
  "job": { "id": "671bb12e8d6c", "title": "Arquiteto OIC - CPFL" },
  "scoring_model_version": "v2",
  "final_score": 84.2,
  "verdict_label": "recommended",
  "must_have_coverage": {
    "covered": 1,
    "total": 1,
    "ratio": 1.0,
    "missing_skills": []
  },
  "score_breakdown": {
    "dimensions": {
      "core_technical_fit": 80,
      "role_fit": 85,
      "context_fit": 95,
      "behavioral_fit": 70,
      "differentials": 60
    },
    "weights": {
      "core_technical_fit": 0.45,
      "role_fit": 0.2,
      "context_fit": 0.15,
      "behavioral_fit": 0.1,
      "differentials": 0.1
    },
    "final_score": 84.2
  },
  "strengths": ["Oracle Integration Cloud", "API Management"],
  "critical_gaps": [],
  "gaps": [],
  "interview_validation": ["Validar profundidade de migração SAP PO → OIC"]
}
```

> Note: fixture scores on disk may still be v1-shaped until reprocessed with `SCORING_MODEL=v2`.

## evaluateCandidate 200

```json
{
  "task_id": "3f2c0a1e-…",
  "kind": "score",
  "status": "queued",
  "progress": 0,
  "message": "Aguardando processamento",
  "redirect_url": null,
  "error": null,
  "scoring_model": "v2",
  "default_scoring_model": "v2"
}
```

## prefillCompensationFromJob 200

```json
{
  "profile": "Arquiteto OIC - CPFL",
  "skills": ["Oracle Integration Cloud", "API Management"],
  "seniority": "senior",
  "allocation_model": "hybrid",
  "target_contract": "PJ",
  "location": { "city": "Campinas", "state": "SP", "country": "BR" },
  "source_job_id": "671bb12e8d6c",
  "source_job_title": "Arquiteto OIC - CPFL",
  "job_compensation_min": 120,
  "job_compensation_max": 150,
  "job_compensation_type": "pj_hour"
}
```

## listCompensationHistory 200

```json
{
  "count": 1,
  "items": [
    {
      "cache_key": "81d56a04f156896175839424213a0971",
      "research_id": "381b7a0c2a26751b",
      "normalized_role": "Arquiteto de Soluções em Nuvem",
      "seniority": "senior",
      "contract_type": "PJ",
      "unit": "hour",
      "median": 214.29,
      "recommended_min": 177.4,
      "recommended_max": 401.83,
      "observations": 10,
      "sources": 9,
      "confidence_level": "HIGH",
      "confidence_score": 0.91,
      "created_at": "2026-08-12T04:04:01+00:00"
    }
  ]
}
```

## researchCompensationAsync 200

```json
{
  "task_id": "a1b2c3d4-…",
  "kind": "compensation_research",
  "status": "queued",
  "progress": 0,
  "message": "Aguardando processamento",
  "redirect_url": null,
  "error": null,
  "result": null
}
```

## getTask 200 (compensation completed)

```json
{
  "task_id": "a1b2c3d4-…",
  "kind": "compensation_research",
  "status": "completed",
  "progress": 100,
  "message": "Pesquisa concluída.",
  "error": null,
  "result": {
    "research_id": "381b7a0c2a26751b",
    "profile": {
      "normalized_role": "Arquiteto de Soluções em Nuvem",
      "seniority": "senior",
      "skills": ["Azure", "AKS", "Kubernetes"]
    },
    "market": {
      "currency": "BRL",
      "unit": "hour",
      "contract_type": "PJ",
      "median": 214.29,
      "recommended_range": { "min": 177.4, "max": 401.83 }
    },
    "sample": { "observations": 10, "sources": 9 },
    "confidence": { "score": 0.91, "level": "HIGH" },
    "sources": [{ "name": "indeed", "url": "https://…", "observations": 1 }],
    "warnings": [],
    "observations": []
  }
}
```

> Cite only fields returned by the API. If `confidence.level` is `LOW` or `sample.observations` is 0, say so honestly — do not invent market numbers.

## 401

```json
{ "detail": "Invalid or missing API key." }
```

## 404

```json
{ "detail": "Candidate not found." }
```
