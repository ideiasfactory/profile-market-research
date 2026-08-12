# Architecture Decision Records (ADRs)

Decisões de arquitetura do Professional Profile Analyser. Status padrão: **Accepted**, salvo indicação em contrário.

| ADR | Título |
| --- | --- |
| [001](ADR-001-separation-between-llm-and-compensation-engine.md) | Separation Between LLM and Compensation Engine |
| [002](ADR-002-search-engine-abstraction.md) | Search Engine Abstraction |
| [003](ADR-003-configurable-search-engine-registry.md) | Configurable Search Engine Registry |
| [004](ADR-004-configurable-crawler-registry.md) | Configurable Crawler Registry |
| [005](ADR-005-glassdoor-crawling-strategy.md) | Glassdoor Crawling Strategy |
| [006](ADR-006-playwright-as-browser-fallback.md) | Playwright as Browser Fallback |
| [007](ADR-007-ollama-on-gpu-server-01.md) | Ollama on gpu-server-01 |
| [008](ADR-008-evidence-based-compensation-extraction.md) | Evidence-Based Compensation Extraction |
| [009](ADR-009-jsonl-for-mvp-persistence.md) | JSONL for MVP Persistence |
| [010](ADR-010-structured-logging-by-research-id.md) | Structured Logging by research_id |
| [011](ADR-011-async-research-with-progress.md) | Async Research with Progress Feedback |
| [012](ADR-012-quality-filters-before-market-stats.md) | Quality Filters Before Market Stats |
| [013](ADR-013-job-sourced-research-prefill.md) | Job-Sourced Research Prefill vs Free-Form |
| [014](ADR-014-load-dotenv-at-startup.md) | Load `.env` at Application Startup |
| [015](ADR-015-compensation-cache-as-ui-history.md) | Compensation Cache as UI History Source |
| [016](ADR-016-open-webui-conversational-frontend.md) | Open WebUI as Conversational Frontend + Cache-Default |
| [017](ADR-017-editable-business-parameter-catalog.md) | Editable Business Parameter Catalog (JSON) |
| [018](ADR-018-inject-business-parameters-into-prompts.md) | Inject Business Parameters into LLM Prompts |
| [019](ADR-019-consolidate-conversational-packages-under-llm-tools.md) | Consolidate Conversational Packages under `llm-tools/` |
| [020](ADR-020-external-api-usage-and-system-settings.md) | External API Usage Dashboard + System Settings Tab |

Visão geral do fluxo de Compensation: [`../architecture.md`](../architecture.md).
