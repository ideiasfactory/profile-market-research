# ADR-021 — Versioned Prompt Management UI

## Status

Accepted

## Context

Prompts LLM lived only as files under `prompts/`. Operators needed to edit them in the product UI, understand each prompt’s purpose, and roll back mistakes without git archaeology.

## Decision

1. Add settings tab **Prompts IA** listing each prompt with title, description, and editable body.
2. Persist managed state in `data/prompt_store.json`, seeding from disk on first access.
3. Every content save creates an immutable new version and marks it active; metadata-only edits update title/description without a content version when text is unchanged.
4. Revert selects a historical version and **copies** it into a new active version (audit trail), rather than deleting history.
5. `load_prompt` / `_read_prompt_file` prefer the active managed version, then fall back to `prompts/*.txt`. Cache clears on save/revert.

## Consequences

- Prompt changes take effect on the next LLM call without redeploy.
- Disk files remain the baseline seed and source of truth for fresh installs.
- Operators can inspect any version via dropdown before reverting.
