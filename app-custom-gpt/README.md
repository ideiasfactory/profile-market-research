# Professional Profile Analyst — Custom GPT Package

custom_gpt_version: 0.2.0

## Objective

Deployment package to configure a **ChatGPT Custom GPT** named **Professional Profile Analyst** as a conversational interface for evidence-based candidate–role evaluation and market compensation research.

It does **not** replace the Professional Profile Analyser application.

## Architecture

```text
User
  ↓
Professional Profile Analyst GPT
  ├── Instructions
  ├── Knowledge
  ├── Code Interpreter
  └── Actions
        ↓
Professional Profile Analyser GPT API (/api/gpt)
        ↓
Scoring Engine (v2 preferred)  +  Compensation Intelligence
        ↓
JSON storage (jobs / candidates / evaluations / compensation cache)
```

### Sources of truth

| Concern | Source of truth |
|---------|-----------------|
| Custom GPT text config (instructions, knowledge, OpenAPI) | **Git repository** |
| Runtime GPT enablement | **GPT Builder** |
| Jobs, candidates, evaluations, deterministic scores, compensation research | **Professional Profile Analyser** |

### Architecture decision

**Decision:** Custom GPT is a complementary interface.

**GPT responsibilities:** conversational UX, interpretation, evidence explanation, comparison narrative, interview assistance, Action orchestration (including compensation research).

**Application responsibilities:** authentication, persistence, deterministic score, compensation orchestration/cache, versioning, business rules, candidate/job lifecycle, audit.

**Consequence:** GPT artifacts can evolve independently without making the prompt the system of record.

Principle: **LLM interprets; application decides.**

## Modes

1. **Standalone** — user pastes JD/resumes; simulation using Knowledge methodology; clearly labeled *not persisted*. No invented market salaries.
2. **Connected** — Actions call `/api/gpt`; API scores and compensation research results are authoritative.

## Package layout

```text
app-custom-gpt/
├── README.md
├── manifest/professional-profile-analyst.yaml
├── instructions/
├── knowledge/
├── actions/          # OpenAPI + auth + catalog + examples
├── conversations/
├── tests/
├── privacy/
└── setup/
```

## How to update Instructions

1. Edit `instructions/instructions.md` (and `action-policy.md`).
2. Bump `instructions_version` in the manifest / release checklist.
3. Paste into GPT Builder → Instructions.
4. Run Preview tests (Bruno/Gabriela conceptual + anti-hallucination, including salary cases).

## How to update Knowledge

1. Edit files under `knowledge/`.
2. Re-upload to GPT Builder (replace previous files).
3. Keep aligned with `app/scoring_config.py` and methodology docs.

## How to configure Actions

1. Ensure app exposes `/api/gpt` (see application README), including `/api/gpt/compensation/*`.
2. Set `PROFESSIONAL_PROFILE_API_KEY` on the server for non-local use.
3. Expose HTTPS base URL (tunnel/prod).
4. Import `actions/openapi.yaml` in GPT Builder.
5. Configure API key / Bearer auth with the secret (never commit it).
6. Smoke-test READ then WRITE / WRITE-like per `tests/action-tests.md` (evaluations + compensation async).

Do **not** point Actions at unauthenticated `/api/v1/compensation/*` — use the GPT-prefixed routes so auth matches other Actions. HTML UI keeps using `/api/v1/compensation/*` without API keys.

## Capabilities recommendation

| Capability | Setting | Why |
|------------|---------|-----|
| Web Search | OFF | No automatic candidate enrichment; pay research goes through Compensation Intelligence Actions |
| Image Generation | OFF | Not required |
| Code Interpreter | ON | Deterministic local score math in standalone |

## How to test

- Manual: `setup/gpt-builder-checklist.md`
- Conceptual: `tests/golden-cases.md`, `tests/anti-hallucination.md`
- Actions: `tests/action-tests.md`
- Application API: `python -m unittest tests.test_gpt_api -v`

## Versioning

Track in Git + `manifest/professional-profile-analyst.yaml` + `setup/release-checklist.md`:

- `custom_gpt_version`
- `instructions_version`
- `knowledge_version`
- `actions_version`
- `methodology_version` (scoring-v2)

## Limitations

- No dedicated compare endpoint (compose from evaluations).
- No delete Actions (`NOT_IMPLEMENTED`).
- Evaluate and compensation research are async (Task + poll); sync compensation exists but often times out in GPT Actions.
- Job/candidate **create** via JSON Actions not exposed yet (UI form flows remain).
- Fixture evaluations may be v1-shaped until reprocessed with v2.
- ChatGPT must reach your API over HTTPS.
- Compensation research quality depends on configured search/crawl providers and may return LOW confidence or empty samples.

## Manual deployment

This package is configured **manually** in GPT Builder (no automatic publish from this repo):

1. Create/edit GPT  
2. Copy Instructions  
3. Set metadata + starters  
4. Upload Knowledge  
5. Enable Code Interpreter; disable Web Search / Image Gen  
6. Import OpenAPI + auth  
7. Run checklists (including compensation smoke test)  
8. Save/publish per workspace policy  

See `setup/gpt-builder-checklist.md`.
