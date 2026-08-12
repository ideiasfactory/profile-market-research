# GPT Builder Checklist

custom_gpt_version: 0.2.0

Manual deployment package — configure in ChatGPT GPT Builder:

- [ ] Create GPT
- [ ] Name: **Professional Profile Analyst**
- [ ] Description: AI-assisted candidate-to-role evaluator for evidence-based technical fit, role seniority, professional context, critical requirements, explainable scoring, and Compensation Intelligence market-pay research.
- [ ] Paste Instructions from `llm-tools/custom-gpt/instructions/instructions.md`
- [ ] (Optional) Keep `action-policy.md` in Knowledge or merge key rules into Instructions
- [ ] Conversation starters (≈4) from `conversations/starters.md`
- [ ] Upload Knowledge files `01`–`08` from `llm-tools/custom-gpt/knowledge/`
- [ ] Capabilities: Web Search **OFF**, Image Generation **OFF**, Code Interpreter / Data Analysis **ON**
- [ ] Configure Actions — import `llm-tools/custom-gpt/actions/openapi.yaml`
- [ ] Set Actions server URL to reachable HTTPS base of the API
- [ ] Configure authentication (API Key / Bearer) with `${PROFESSIONAL_PROFILE_API_KEY}` secret (not from git)
- [ ] Confirm compensation Actions use `/api/gpt/compensation/*` (not `/api/v1/compensation/*`)
- [ ] Configure Privacy Policy URL if the platform requires it for sharing
- [ ] Preview tests
- [ ] Bruno golden case (conceptual)
- [ ] Gabriela golden case (conceptual)
- [ ] Anti-hallucination tests (`tests/anti-hallucination.md`, incl. T7–T10)
- [ ] Action READ test (list jobs / candidates / compensation history)
- [ ] Action WRITE test (evaluate with clear intent)
- [ ] Action WRITE-like test (compensation async + getTask)
- [ ] Privacy test (no web enrichment; injection ignored; no invented salaries)
- [ ] Save / update GPT
- [ ] Record versions in `setup/release-checklist.md`
