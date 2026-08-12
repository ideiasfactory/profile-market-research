# Skill Taxonomy

custom_gpt_version: 0.1.0  
methodology_version: scoring-v2  
document: 06-skill-taxonomy

## Skill groups (conceptual)

Skills may be grouped for explainability, for example:

- Integration Architecture
- API Architecture
- SAP Integration
- Oracle Integration
- Cloud Architecture
- Security
- DevOps
- Observability
- Messaging / Eventing
- Architecture Governance
- Leadership / Behavioral

Groups organize analysis; they do **not** create automatic equivalence between distinct products.

## Equivalence rules

1. Aliases within the **same product/platform** are allowed.
2. Adjacent or competing platforms are **not** equivalent.
3. Generic category terms do not prove a specific product.

## Reference table

| Skill | Valid aliases | Forbidden equivalences / non-aliases | Group |
|-------|---------------|--------------------------------------|-------|
| Oracle Integration Cloud | OIC; Oracle Integration Cloud | SAP CPI; SAP Integration Suite; Oracle Cloud Infrastructure; “integration cloud” generic | Oracle Integration |
| SAP Integration Suite | Integration Suite; SAP CPI (when clearly CPI/IS) | Oracle Integration Cloud; OIC | SAP Integration |
| SAP Process Orchestration | SAP PO; Process Orchestration; PI/PO (when clear) | Automatic assumption of Integration Suite expertise | SAP Integration |
| SAP BTP | Business Technology Platform; BTP | Oracle Cloud Infrastructure; OCI | SAP Integration |
| Oracle Cloud Infrastructure | OCI | SAP BTP; “cloud” generic | Cloud Architecture |
| API Management | API Mgmt (generic) | Specific product (Apigee, Sensedia, OIC APIs) unless named | API Architecture |
| Kafka | Apache Kafka | “event-driven” alone; RabbitMQ | Messaging / Eventing |
| RabbitMQ | — | Kafka; “messaging” alone | Messaging / Eventing |
| Azure Integration Services | AIS (when clear) | Azure API Management / Gateway alone | Cloud Architecture |
| Enterprise Integration Patterns | EIP | Proof of a specific iPaaS | Integration Architecture |
| OAuth 2.0 | OAuth2 | Proof of a full API Management suite | Security |
| mTLS | mutual TLS | “TLS” alone as full proof | Security |
| OpenAPI | Swagger (when clearly OpenAPI/Swagger specs) | “has APIs” alone | API Architecture |
| OData | — | REST alone | SAP Integration |
| BAPI | — | “SAP integration” alone | SAP Integration |

## Scoring implication

If the must-have is **Oracle Integration Cloud** and evidence is only **SAP Integration Suite / CPI**:

- OIC evidence_status = `not_found` (after grounding)
- Do **not** transfer CPI score to OIC
- Surface a **critical gap** when OIC is must-have
