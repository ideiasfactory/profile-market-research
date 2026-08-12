# Release Checklist

custom_gpt_version: 0.2.0

Version Custom GPT independently from the application.

## Release record

| Field | Value |
|-------|-------|
| GPT name | Professional Profile Analyst |
| custom_gpt_version | 0.2.0 |
| instructions_version | 1.1 |
| knowledge_version | 1.1 |
| actions_version | 1.1 |
| methodology_version | scoring-v2 |
| API compatibility | `/api/gpt` (+ tasks + `/api/gpt/compensation/*`) |
| last_updated | 2026-08-12 |
| owner | [team] |
| git commit | [fill on release] |

## Pre-release

- [ ] Instructions reviewed (incl. compensation anti-hallucination)
- [ ] Knowledge files consistent with app scoring_config + compensation context
- [ ] OpenAPI validated (paths match live `/api/gpt` routes)
- [ ] No secrets in git
- [ ] No unnecessary PII in Knowledge
- [ ] Action catalog matches live API
- [ ] Golden cases reviewed (Bruno / Gabriela conceptual)
- [ ] Anti-hallucination pack passed in Preview (T7–T10 salary cases)
- [ ] READ Action smoke test
- [ ] WRITE Action smoke test — evaluate (staging)
- [ ] WRITE-like Action smoke test — compensation async + poll (staging)
- [ ] Privacy policy URL ready if sharing publicly

## Post-release

- [ ] Tag git: `app-custom-gpt-v0.2.0`
- [ ] Note GPT Builder update date
- [ ] Communicate changes to users
