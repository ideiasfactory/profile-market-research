# Golden Cases

custom_gpt_version: 0.1.0  
tests_version: 1.0

> Conceptual expectations only — **do not hardcode final scores**.

## CASE-001 — Bruno × Arquiteto OIC CPFL

See `knowledge/08-reference-cases.md`.

Expect recognition of OIC, integration architecture, SAP PO, API Management, leadership, CPFL context. Supporting doc gaps (CORS, BAPI, …) should not alone collapse the case.

## CASE-002 — Gabriela × Arquiteto OIC CPFL

Strong SAP Integration Suite / BTP / SAP integration stack. OIC = not_found. Critical OIC gap. Never CPI→OIC transfer.

## CASE-003 — Excellent architect, no OIC

Synthetic: deep integration architecture, no OIC mention.

**Expected:** Critical OIC gap when OIC is must-have; architecture Role Fit may still be strong.

## CASE-004 — OIC specialist without architecture ownership

Synthetic: deep OIC configuration/development, no architecture/stakeholder ownership.

**Expected:** Strong tool fit; limited Role Fit for architect JD.

## CASE-005 — Keyword salad

Synthetic: many buzzwords without delivery evidence.

**Expected:** Low/moderate scores; reduced confidence; prefer `inferred`/`not_found` over 4–5.

## CASE-006 — Soft skills absent

Synthetic: strong technical evidence; no behavioral examples.

**Expected:** Soft skills `needs_validation`, score null; not automatic zero in v2 methodology.
