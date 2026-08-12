# Evidence Policy

custom_gpt_version: 0.1.0  
methodology_version: scoring-v2  
document: 03-evidence-policy

## Principles

1. Evidence before inference.
2. Absence of evidence ≠ absence of competence.
3. Avoid score inflation — score 5 requires exceptional, strong evidence.
4. Every scored competence needs evidence, source, and confidence when claimed.

## Score scale (0–5)

| Score | Meaning |
|------:|---------|
| 0 | No usable evidence |
| 1 | Basic contact / mention only |
| 2 | Limited exposure |
| 3 | Practical experience |
| 4 | Strong / recurring experience |
| 5 | Specialist or exceptional evidence |

## Confidence (0–1)

Estimate how reliable the mapping from text → skill is.

- High confidence: named platform + role ownership + concrete outcomes
- Low confidence: keyword-only, vague “worked with integrations”, inferred adjacency

## Evidence status

| Status | Meaning |
|--------|---------|
| `explicit` | Directly stated in resume/JD/API evidence |
| `inferred` | Weak implication; prefer interview validation |
| `not_found` | No usable evidence located |
| `negative` | Contradictory or opposing evidence |
| `needs_validation` | Especially soft skills without behavioral support |

## Distinctions

| Situation | Correct handling |
|-----------|------------------|
| Skill not mentioned | `not_found` — do **not** claim “does not know” |
| Resume says “no experience with X” | `negative` |
| “Cloud integration projects” for specific OIC claim | `inferred` or `not_found` — not automatic OIC |
| “Led OIC migration for utilities client” | `explicit` with high confidence |
| Soft skill with no behavioral example | `needs_validation`, `score = null` |

## Sources

Prefer:

1. Resume text authorized by the user / application
2. Job analysis criteria
3. Persisted evaluation evidence from the API

Do **not** silently enrich from the public web.

## Anti-inflation checklist

Before assigning 4–5:

- Is the platform/product named?
- Is the candidate’s ownership clear (architect vs peripheral)?
- Is there recurrence or depth (not a single buzzword)?
- Are adjacent technologies being wrongly equated?
