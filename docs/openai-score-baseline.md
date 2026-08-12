# Baseline de custo — score via OpenAI

Baseline de planejamento/custo para avaliações de score (`score_candidate`) com provedor OpenAI, após smoke test PO bem-sucedido.

## Métrica de negócio

**US$ 0.04 por avaliação de score** (arredondado a partir de ~US$ 0.038 medido no sample).

Usar este valor para estimativas de volume, orçamento e comparação com LLM local.

## Sample técnico (referência)

| Campo | Valor |
| --- | --- |
| Data | 2026-08-12 (~15:23 local / 18:23 UTC) |
| Provider / modelo | `openai` / `gpt-4.1` |
| Método | `llm` |
| Chamadas API | 4 (`score_skills` ×2, `score_fit`, `score_narrative`) |
| Tokens | ~11 030 prompt / 1 971 completion / 13 001 total |
| Custo estimado (tabela env) | ~US$ 0.038 → baseline de negócio **US$ 0.04** |

Preços usados no metering: `OPENAI_PRICE_INPUT_PER_1M` / `OPENAI_PRICE_OUTPUT_PER_1M` (defaults documentados no README).

## Caveats

- O custo escala com o número de batches de skills e com o tamanho do currículo + JD no prompt.
- O valor em USD é estimado pela tabela de preços do `.env`, não pela fatura OpenAI em tempo real.
- O dashboard OpenAI (Usage/Billing) pode atrasar em relação a `data/llm_usage.jsonl`.
- Compensation Intelligence **não** entra neste baseline (permanece em Ollama, ADR-001).

## Onde ver métricas ao vivo

- UI **APIs Externas**: `/external-apis`
- Log append-only: `data/llm_usage.jsonl`
- Por score: campo `audit.usage` no JSON de avaliação
- API: `GET /api/llm/usage` (e resumo agregado em `GET /api/v1/external-apis/usage`)
