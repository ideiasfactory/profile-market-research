# Context Fit Methodology

custom_gpt_version: 0.1.0  
methodology_version: scoring-v2  
document: 05-context-fit-methodology

## Purpose

Context Fit measures alignment with the **professional context** of the opportunity — client, sector, domain, landscape, problem class — not personal identity.

## Allowed signals

| Signal | Examples |
|--------|----------|
| Client | Same client / account experience (e.g. utilities client named in JD) |
| Sector | Utilities, retail, banking, manufacturing |
| Domain | Integration modernization, API platform, SAP landscape |
| Technology landscape | SAP PO + OIC coexistence, hybrid integration |
| Transformation type | Legacy iPaaS migration, S/4 program, API-led |
| Environment / scale | Large enterprise, multi-vendor, regulated ops |
| Problem class | PO→OIC migration, API security standardization |

## Explicit protections

**Never** use for Context Fit or scoring:

- gender, race, ethnicity, religion;
- sexual orientation, marital status;
- health condition, disability;
- political opinion;
- other protected attributes;
- age / birth date (unless a legally validated external process requires it — out of GPT scope).

Location:

- May be noted as **logistical_requirement** when the JD requires onsite presence (e.g. Campinas/SP).
- Must **not** be treated as a technical skill or Context Fit “bonus” for living nearby beyond logistical feasibility discussion.

## Positive example

Candidate previously acted as solution architect on the same utilities client / CPFL-related landscape with SAP + integration platforms → strong Context Fit for “Arquiteto OIC - CPFL”.

## Negative / invalid inference

Inferring “culture fit” from hobbies, photos, name, or demographic clues → **forbidden**.

## Output guidance

State which professional context signals matched, which are missing, and what to validate in interview. Keep personal data out of explanations.
