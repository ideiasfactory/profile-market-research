# ADR-002 — Search Engine Abstraction

Decision: all search providers implement `SearchEngine.search()` and return canonical `SearchResult`.

Reason: provider-specific APIs must not leak into the domain or orchestrator.
