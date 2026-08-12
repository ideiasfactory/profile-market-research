# Backlog

Itens de follow-up / nice-to-have. Não bloqueiam features em andamento.

## BL-001 — Usar Project secret key no OpenAI (não User/Legacy)

| Campo | Valor |
| --- | --- |
| **Prioridade** | Agora / ação do PO (desbloqueia uso do provider OpenAI) |
| **Urgência** | Alta para começar a usar OpenAI; baixa em código (já pronto) |
| **Status** | Aberto (ops / dashboard) |

### Contexto

No dashboard OpenAI:

- **User API Keys** = Legacy (discontinuado para o uso preferencial novo).
- **Project API Keys** = modelo atual; UI: **"+ Create new secret key"**.

A app já autentica com `OPENAI_API_KEY` como Bearer — **não há mudança de código** para usar uma Project secret key hoje. Basta criar a key no projeto e colocar no `.env`.

### Agora / PO

1. No OpenAI dashboard, aba **Project API Keys** (não User/Legacy).
2. **+ Create new secret key**.
3. Colocar o valor em `OPENAI_API_KEY` (`.env` / settings).

### Fora de escopo deste item

Service account (identidade/rotação) = hardening opcional — ver BL-002. Não bloqueia o uso do OpenAI.

## BL-002 — Documentar/recomendar Service Account (opcional)

| Campo | Valor |
| --- | --- |
| **Prioridade** | Backlog / nice-to-have (pós uso com Project secret key) |
| **Urgência** | Baixa — hardening/ops; Project key já basta para operar |
| **Status** | Aberto |

### Contexto

Hoje `OPENAI_API_KEY` (Bearer) funciona com Project secret key ou secret de service account. Como follow-up, migrar documentação/ops para recomendar explicitamente **service account** (identidade de app, rotação, isolamento de projeto).

### Escopo sugerido

- Documentar setup de service account na OpenAI.
- Garantir que `.env.example` / README recomendem service account secret como caminho preferido de longo prazo.
- Avaliar se há mudança de auth além de API key (hoje não há).
- Eventual rotação / secrets management.

## BL-003 — Gráfico multi-score (comparativo visual Local vs OpenAI)

| Campo | Valor |
| --- | --- |
| **Prioridade** | Backlog / nice-to-have |
| **Urgência** | Baixa — histórico tabular já cobre A/B sem perda de dados |
| **Status** | Aberto (adiado) |

### Contexto

Com score history, o PO já compara runs (quando, provider, modelo, score, veredito, método, custo) na página Scores e via API. Falta um **gráfico** que plote duas (ou N) execuções do mesmo par lado a lado (ex.: radar/barras Local vs OpenAI).

### Escopo sugerido

- Selecionar 2+ entradas do histórico (ou atual + histórico) e sobrepor eixos no chart existente.
- Não alterar o contrato de score; só UX de comparação.
