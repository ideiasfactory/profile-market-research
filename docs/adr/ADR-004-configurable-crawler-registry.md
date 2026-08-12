# ADR-004 — Configurable Crawler Registry

Decision: crawlers are resolved through `ProviderRegistry`, ordered by priority, with `GenericCrawler` fallback.

Reason: source-specific behavior belongs in adapters, not in the orchestrator.
