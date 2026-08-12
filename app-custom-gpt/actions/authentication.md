# Authentication for GPT Actions

custom_gpt_version: 0.2.0  
actions_version: 1.1

## Current application auth

Professional Profile Analyser supports an **optional API key** for the JSON surface:

- Routes under `/api/gpt/*` check `PROFESSIONAL_PROFILE_API_KEY` (jobs, candidates, evaluations, **compensation**, tasks).
- If the env var is **unset/empty**, requests are allowed (local MVP).
- If set, require one of:
  - `Authorization: Bearer ${PROFESSIONAL_PROFILE_API_KEY}`
  - `X-API-Key: ${PROFESSIONAL_PROFILE_API_KEY}`

HTML UI routes remain unauthenticated (trusted local/network MVP), including `GET /compensation`.

Unauthenticated Compensation Intelligence JSON (`/api/v1/compensation/*` and `GET /api/tasks/{task_id}`) remains available for the HTML UI. **GPT Actions must not use those paths** — use `/api/gpt/compensation/*` and `/api/gpt/tasks/{task_id}` so auth policy matches other GPT Actions.

## GPT Builder configuration (manual)

1. Deploy or tunnel the API with HTTPS (ChatGPT Actions require a reachable HTTPS base URL).
2. Set server env: `PROFESSIONAL_PROFILE_API_KEY=<strong random secret>`.
3. In GPT Builder → Actions → Authentication:
   - Prefer **API Key** header `X-API-Key`, **or**
   - **Bearer** token with the same secret.
4. Store the secret only in the GPT Builder / secret store — **never in Git**.

Placeholder used in docs:

```text
${PROFESSIONAL_PROFILE_API_KEY}
```

## OAuth evolution

Per-user OAuth is **not** implemented. If individual authorization becomes required (multi-tenant SaaS), document and implement OAuth separately. Do not invent OAuth for this package.

## Security notes

- Do not commit real keys.
- Rotate keys if exposed.
- Prefer private GPT + private network / allowlisted tunnel for candidate data.
- Minimize `include_resume=true` usage.
