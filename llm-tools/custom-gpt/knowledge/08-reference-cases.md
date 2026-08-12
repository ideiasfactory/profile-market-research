# Reference Cases (Conceptual Benchmarks)

custom_gpt_version: 0.1.0  
methodology_version: scoring-v2  
document: 08-reference-cases

> These are **conceptual golden cases**, not hardcoded scores.  
> Use fixtures / authorized resumes in the application. Do not embed personal contact data here.

Fixture job: **Arquiteto OIC - CPFL** (integration solution architect; OIC must-have; SAP landscape awareness; architecture focus, not ABAP development).

---

## CASE-001 — Bruno Libanio × Arquiteto OIC CPFL

### Recognize as strong (when evidenced in resume)

- Oracle Integration Cloud (OIC)
- Integration / solution architecture
- SAP Process Orchestration (SAP PO)
- API Management
- Technical leadership / architecture ownership
- Professional context with CPFL / utilities landscape → Context Fit signal

### Do not sink solely for documentary absence of supporting details such as

- CORS
- BAPI
- OpenAPI
- OData
- mTLS

Supporting gaps may be listed; they should not automatically dominate over strong OIC + architecture + context evidence.

### Conceptual expectation

Solid tool + role + context story relative to this JD; supporting documentation gaps are secondary. Exact `final_score` must come from the engine / simulation, never from this file.

---

## CASE-002 — Gabriela Rocha de Paula × Arquiteto OIC CPFL

### Recognize as strong (when evidenced)

- SAP Integration Suite / CPI
- SAP BTP
- S/4HANA / ECC landscape experience
- OData, BAPI, REST, SOAP
- OAuth2, mTLS (when present)
- EDA / Kafka / RabbitMQ (when present)
- Deep SAP integration capability

### Critical non-equivalence

- Oracle Integration Cloud = **NOT_FOUND** unless explicitly evidenced
- Never treat SAP CPI / Integration Suite as OIC evidence

### Conceptual expectation

Strong **SAP Integration Fit** + **critical OIC gap** for this must-have. Role may skew more developer/SAP specialist than OIC solution architect depending on evidence — call that out without inventing OIC.

---

## How to use

- Regression / prompt QA benchmarks
- Anti-hallucination checks (CPI ≠ OIC)
- Calibration of explainability narratives

Never publish phone numbers, emails, or other unnecessary personal data from resumes into Knowledge files.
