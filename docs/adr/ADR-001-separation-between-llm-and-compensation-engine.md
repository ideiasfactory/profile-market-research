# ADR-001 — Separation Between LLM and Compensation Engine

Decision: the LLM extracts structured observations only. Python performs salary normalization, CLT/PJ conversion, outlier detection, percentiles and confidence.

Reason: market estimates must be reproducible and auditable.
