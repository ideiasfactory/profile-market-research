# Backlog

Itens de follow-up / nice-to-have. Não bloqueiam features em andamento.

## BL-001 — Migrar autenticação OpenAI para service account

| Campo | Valor |
| --- | --- |
| **Prioridade** | Backlog / nice-to-have (pós `feature/openai-llm-provider`) |
| **Urgência** | Baixa — as keys atuais já funcionam; hardening/ops |
| **Status** | Aberto |

### Contexto

Hoje a app usa `OPENAI_API_KEY` (Bearer) — funciona com project key ou service account secret. O PO quer, como follow-up, migrar formalmente para o modelo de **service account** (mais robusto: identidade de app, rotação, isolamento de projeto).

### Escopo sugerido

- Documentar setup de service account na OpenAI.
- Garantir que `.env.example` / README descrevam service account como caminho recomendado.
- Avaliar se há mudança de auth além de API key (hoje não há).
- Eventual rotação / secrets management.
