# Product Context — Professional Profile Analyser

custom_gpt_version: 0.2.0  
knowledge_version: 1.1  
document: 01-product-context

## Objective

Professional Profile Analyser is an application that helps hiring teams evaluate technology candidates against specific opportunities using:

- structured job understanding;
- evidence extracted from resumes;
- deterministic scoring models (v1 / v2);
- explainable strengths, gaps, and interview validation;
- **Compensation Intelligence** — evidence-based market pay research for roles (Connected mode via GPT Actions).

## Main entities

| Entity | Role |
|--------|------|
| **Job** | Opportunity with JD, profile, seniority, compensation metadata, ideal candidate context, and analysis |
| **Candidate** | Person with reported role, city, source metadata, and resume text |
| **Resume** | Not a separate entity; stored as `resume_text` (+ source) on Candidate |
| **Job Analysis** | Structured interpretation: role intent, tiers (must-have/core/supporting/differentials), soft skills, skill groups |
| **Candidate Evaluation (Score)** | Persisted result of candidate × job scoring |
| **Evidence** | Snippets + `evidence_status` + confidence supporting each skill score |
| **Interview Validation** | Suggested questions to validate gaps / soft skills |
| **Task** | Async job for LLM-backed analyse/extract/score **or** compensation research |
| **Compensation Research** | Cached market-pay result: normalized profile, market stats, sample size, confidence, sources, observations, warnings |

## Compensation Intelligence (brief)

- Inputs: profile title, skills, seniority, allocation (onsite/hybrid/remote), location, target contract (`CLT` / `PJ`), optional `source_job_id`.
- Outputs: recommended range and distribution in the returned unit (often hourly for PJ), confidence level, source list, optional observation rows, warnings (e.g. blocked/paywalled sources).
- GPT must cite **only** API evidence — never invent salaries. Prefer job prefill when discussing a stored open job.
- Prefer async research + task poll; sync may time out on cold runs.

## Versioning

- Job analysis version: typically `2`
- Scoring model version: `v1` (flat) or `v2` (hierarchical composite — preferred)
- Prompt versions tracked in application audit metadata
- Custom GPT artifacts versioned in Git independently of GPT Builder UI
- Compensation research payloads are versioned by cache / `research_id` in application storage

## Relation: Custom GPT ↔ Application

| Component | Responsibility |
|-----------|----------------|
| **Custom GPT** | Conversational UX, interpretation, explanation, comparison narrative, interview assistance, Action orchestration |
| **Application API** | System of record: persistence, deterministic score, compensation research orchestration/cache, versioning, business rules, audit |
| **Scoring Engine** | Computes scores from evidence + configured weights |
| **Compensation Intelligence** | Search/crawl/normalize salary observations → market stats |
| **Storage** | JSON stores for jobs, candidates, evaluations, compensation cache |

### Explicit boundaries

- Custom GPT ≠ database
- Custom GPT ≠ scoring system of record
- Custom GPT ≠ salary database
- Custom GPT = reasoning / orchestration / conversational interface

Principle: **LLM interprets; application decides.**

## Modes

1. **Standalone** — user pastes JD/resumes; GPT simulates methodology; result not persisted. No invented market salaries.
2. **Connected** — Actions read/write the Professional Profile Analyser API; persisted scores and compensation research results are authoritative.
