# ADR-022 — Unit Tests Must Not Call Paid LLM APIs

## Status

Accepted

## Context

The product can call paid LLM providers (OpenAI Chat Completions) for `analyse_job`, `extract_candidate`, and `score_*`. Usage is metered in `data/llm_usage.jsonl` and billed against the project API key.

Unit / CI tests that accidentally hit the real OpenAI API would:

- spend real money on every test run;
- make CI flaky (network, quotas, model availability);
- leak or depend on secrets (`OPENAI_API_KEY`) in developer/CI environments;
- pollute local metering logs and cost baselines.

Existing unit tests already prefer mocks (`AsyncMock` on `json_completion_with_audit`, `httpx.AsyncClient` patches, fake `OPENAI_API_KEY=sk-test`). This ADR makes that rule explicit and mandatory.

Local/Ollama calls in unit tests are also discouraged for speed and determinism; if exercised, they must be mocked the same way. Live Local vs OpenAI comparisons belong in manual/smoke runs or documented baselines (e.g. `docs/openai-score-baseline.md`), not in `unittest`.

## Decision

1. **Unit tests (`tests/`, especially `tests/unit/`) must never perform real network calls to paid LLM providers** (OpenAI or any future billed Chat Completions-compatible endpoint used as `llm_provider=openai`).
2. When a test needs OpenAI (or paid-provider) behavior, **mock the boundary**:
   - prefer mocking `LLMClient.json_completion` / `json_completion_with_audit`;
   - or patch `httpx.AsyncClient` / transport used by `OpenAILLM`;
   - or patch orchestration entry points (`run_score_task`, `get_llm`, `recalibrate_skill_weights`, etc.).
3. Tests may construct `OpenAILLM` / call `get_llm("openai")` only if they **do not** invoke a live completion (e.g. factory resolution, `configured=False` without key).
4. Do **not** rely on a real `OPENAI_API_KEY` from `.env` for unit tests. Use empty key, `sk-test`, or env patches scoped to the test.
5. **Manual / smoke / PO A/B runs** against live OpenAI remain allowed outside the unit suite and should be recorded in ops docs (cost baselines), not automated as unpaid CI unit tests.
6. If an integration suite that hits live paid APIs is ever added, it must be **opt-in** (separate path, explicit env flag, never part of default `python -m unittest discover`), with clear cost warnings.

## Consequences

- CI and local `unittest` stays free of OpenAI spend and network flakiness.
- Paid-provider coverage is still possible via mocks (JSON payloads, usage fields, error paths).
- Developers must not “quick test” real OpenAI from unit tests; use the app UI/API or documented smoke procedures instead.
- Reviewers should reject PRs whose unit tests call live OpenAI (or remove secrets/network as a hard requirement for green CI).
