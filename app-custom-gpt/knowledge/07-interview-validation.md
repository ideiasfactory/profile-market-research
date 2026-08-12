# Interview Validation

custom_gpt_version: 0.1.0  
methodology_version: scoring-v2  
document: 07-interview-validation

## Purpose

Generate questions that elicit **concrete evidence**, not yes/no familiarity claims.

## When to generate questions

- Must-have partial
- Must-have missing
- Low confidence evidence
- `needs_validation` (especially soft skills)
- Critical gaps
- Ambiguous role / seniority ownership
- Inconsistencies across resume sections
- Important technology named without depth

## Prefer / avoid

| Prefer | Avoid |
|--------|-------|
| “Descreva uma arquitetura OIC pela qual você foi responsável e quais decisões arquiteturais tomou.” | “Você conhece OIC?” |
| “Conte um caso em que você definiu o target architecture de migração PO → iPaaS e como mediu risco.” | “Já trabalhou com integração?” |
| “Como você conduziu trade-offs entre sincronismo, resiliência e governança de APIs neste landscape?” | “Tem soft skills de liderança?” |

## Templates by trigger

### Must-have missing / critical gap

Ask for a specific delivery: platform, scope, decisions, constraints, outcome.

### Must-have partial

Probe depth: ownership vs participation; production vs lab; architecture vs configuration only.

### Low confidence / inferred

Ask for an artifact-level story (patterns used, failure modes, security controls).

### Soft skill needs_validation

Ask for a behavioral STAR-style episode tied to architecture stakeholders.

### Role / seniority ambiguity

Ask who approved the architecture, what the candidate decided alone, and how conflict was resolved.

## Output format

Provide a short prioritized list (typically 3–7 questions), each mapped to the gap it validates.
