# Data Handling

custom_gpt_version: 0.2.0  
privacy_version: 1.1

## Principles

- Data minimization
- Purpose limitation (candidate–role evaluation and market-pay research)
- Resumes are sensitive personal data
- Application is system of record; GPT is an interface

## Resume / CV handling

- Prefer application storage over repeating full CV text in chat
- Use `include_resume=true` only when evidence inspection requires it
- Do not copy unnecessary PII (phone, email, address, documents) into Knowledge or public fixtures
- Do not log secrets or full CVs into git

## Actions

- Transmit only fields needed for the user question
- Prefer evaluation summaries over full item dumps
- Prefer compensation history/result summaries; use `include_observations=true` only when citing individual salary evidence rows
- Never place API keys in prompts or knowledge files
- Use `/api/gpt/*` (including compensation) with API key auth when configured — not unauthenticated UI JSON routes

## Compensation research

- Market research may query third-party job/salary sources via the application (not ChatGPT Web Search)
- Report API warnings about blocked/paywalled sources; do not attempt to bypass CAPTCHA or paywalls
- Do not invent salary figures when research fails or returns LOW/empty samples

## Scoring fairness

- No protected attributes in scoring or Context Fit
- Location only as logistical requirement when JD requires it (or as an explicit market-research filter)

## Web enrichment

- Disabled by default (ChatGPT Web Search OFF)
- Do not search LinkedIn/Google/news to alter scores without explicit user request and appropriate policy
- Market pay must go through Compensation Intelligence Actions, not ad-hoc web browsing

## Private GPT

This Custom GPT is intended primarily as a **private / internal** deployment. If published more broadly with Actions, publish an accessible privacy policy URL and review platform requirements.
