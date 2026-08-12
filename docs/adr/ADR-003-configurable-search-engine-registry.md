# ADR-003 — Configurable Search Engine Registry

Decision: search engines are resolved through `ProviderRegistry` using YAML and environment overrides.

Reason: providers must be enabled, disabled and replaced without changing orchestration logic.
