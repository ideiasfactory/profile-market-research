# Scoring Methodology (v2)

custom_gpt_version: 0.1.0  
methodology_version: scoring-v2  
document: 02-scoring-methodology

## Preferred model

`scoring_model: v2` (application default via `SCORING_MODEL`).

`v1` remains available as a flat weighted average of skill rows (legacy).

## Dimension weights (defaults — configurable)

| Dimension | Default weight | Contents |
|-----------|----------------|----------|
| Core Technical Fit | **45%** | Must-have + core + supporting technical skills |
| Role / Seniority Fit | **20%** | Role alignment, ownership, architecture scope |
| Context Fit | **15%** | Professional context only |
| Behavioral Fit | **10%** | Soft skills with evidence |
| Differentials | **10%** | Nice-to-have differentiators |

These are **defaults**. Environment/configuration in the application may override them.

When Connected, **weights recovered from the application / evaluation payload prevail**.

If differentials or behavioral dimensions are empty, the application redistributes weight across remaining dimensions.

## Skill tier weights (defaults — configurable)

| Tier | Default weight | Typical range |
|------|----------------|---------------|
| MUST_HAVE | ~10 | 8–10 |
| CORE | ~6–7 | 6–7 |
| SUPPORTING | ~2–3 | 2–3 |
| DIFFERENTIAL | ~1–2 | 1–2 |
| SOFT | ~3 | 1–5 |

Do not treat these as universal laws if the job analysis or application config stores different weights.

## Skill score scale

Each skill uses **0–5** (or `null` for soft skills awaiting validation).

Composite dimensions and final score are expressed as **0–100**.

## Soft skills (v2)

- Missing evidence → `score: null`, `evidence_status: needs_validation`
- Excluded from the scoring denominator (not forced to zero)

## Must-have handling (v2)

- Covered when skill score ≥ configured minimum (default **3** on 0–5 scale)
- Coverage ratio = covered / total must-haves
- Weak/missing/`not_found`/`negative` must-haves → **critical gaps**
- Auto-eliminate on critical gap: **default false** (configurable)

## Verdict labels (v2 defaults)

| Label | Typical rule of thumb |
|-------|------------------------|
| `strong_fit` | High score (e.g. ≥85) and solid must-have coverage |
| `recommended` | Good score (e.g. ≥70) with acceptable coverage |
| `evaluate` | Mid score — interview needed |
| `not_recommended` | Low score / zero must-have coverage (per app rules) |

Exact thresholds live in application config (`VERDICT_*`). Prefer API `verdict_label` when Connected.

## Connected vs Standalone

| Mode | Score source |
|------|--------------|
| Connected | Use API `final_score`, `score_breakdown`, `verdict_label` |
| Standalone | Simulate with this methodology; label **not persisted**; use Code Interpreter for arithmetic |

Never hardcode golden-case final scores in prompts or knowledge.
