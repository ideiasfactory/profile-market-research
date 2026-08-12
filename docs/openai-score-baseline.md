# Baseline de custo e comparativo — score Local vs OpenAI

Baseline de planejamento/custo para avaliações de score (`score_candidate`) com provedor OpenAI, mais **comparativo de performance e resultado** versus LLM local (mesmo par vaga/candidato), após smoke tests PO.

## Métrica de negócio (OpenAI)

**US$ 0.04 por avaliação de score** (arredondado a partir de ~US$ 0.038 medido no sample).

Usar este valor para estimativas de volume, orçamento e comparação com LLM local (custo de API ≈ US$ 0; custo real = infraestrutura/GPU).

## Comparativo de negócio — quando usar cada um

| Critério | Local (`qwen2.5:14b`) | OpenAI (`gpt-4.1`) |
| --- | --- | --- |
| Custo / avaliação (API) | **US$ 0** (só infra/GPU) | **~US$ 0.04** (baseline) |
| Latência (sample A/B) | **~2,3–2,6 min** (task completa) | **~17 s** só nas 4 chamadas LLM; task completa tipicamente ≪ local |
| Qualidade de método (sample) | `hybrid` (1/2 batches de skills não usable → fallback heurístico) | `llm` (todos os batches de skills OK) |
| Privacidade / dados | Currículo permanece on-prem | Currículo enviado à API OpenAI |
| Quando preferir | Volume alto, dados sensíveis, custo zero de API, GPU disponível | Smoke de qualidade, baixa latência, batches LLM estáveis, validação vs local |

**Leitura de negócio (sample único):** OpenAI é ~**8–9× mais rápido** no trecho LLM e ~**US$ 0.04** por score; local é **grátis na API**, mas mais lento e, neste A/B, com sinal de qualidade pior (`hybrid` vs `llm`).

## Sample técnico OpenAI (referência de custo)

| Campo | Valor |
| --- | --- |
| Data | 2026-08-12 (~15:23 local / 18:23 UTC) |
| Provider / modelo | `openai` / `gpt-4.1` |
| Método | `llm` |
| Chamadas API | 4 (`score_skills` ×2, `score_fit`, `score_narrative`) |
| Tokens | ~11 030 prompt / 1 971 completion / 13 001 total |
| Custo estimado (tabela env) | ~US$ 0.038 → baseline de negócio **US$ 0.04** |
| Wall das 4 calls | ~16,6 s (`llm_usage.jsonl` 18:23:17 → 18:23:33 UTC) |

Preços usados no metering: `OPENAI_PRICE_INPUT_PER_1M` / `OPENAI_PRICE_OUTPUT_PER_1M` (defaults documentados no README).

## Comparativo técnico A/B (mesmo par)

Par: **Bruno Libanio** · `job_id=671bb12e8d6c` · `candidate_id=e475d1052f49` · scoring **v2**.

| Campo | OpenAI (~15:23) | Local (~15:34) |
| --- | --- | --- |
| `llm_provider` | `openai` | `local` |
| Modelo | `gpt-4.1` | `qwen2.5:14b` |
| `method` | `llm` | `hybrid` |
| `final_score` | *não retido* (arquivo sobrescrito pelo run local) | **54.9** |
| `verdict_label` | *não retido* | **evaluate** |
| `must_have_coverage` | *não retido* | 1/1 (ratio 1.0, OIC) |
| Tokens / custo API | 13 001 · ~US$ 0.038 | n/a · **US$ 0** API |
| Latência | ~16,6 s (só LLM calls) | ~139 s até `scored_at` / ~154 s task (`b71a5004-…`) |
| Sinal de qualidade | 2/2 batches skills usable; fit/narrative sem erro | batch0 skills `usable=false` → heurística; batch1 OK; fit/narrative OK |

### Resultado comparativo / alinhamento entre engines

Isto **não** é acurácia absoluta vs label humano: não há gold label para este candidato/vaga em `tests/test_benchmark_cases.py` (benchmarks cobrem regras de veredito/heurística, não este A/B).

Proxies honestos neste sample:

1. **Método:** OpenAI `llm` vs Local `hybrid` — desacordo de qualidade de pipeline (local precisou de fallback heurístico em um batch de skills).
2. **Score / veredito numéricos:** só o lado local permanece no disco (`54.9` / `evaluate`). O JSON OpenAI foi sobrescrito; **delta de score e acordo de veredito não são mensuráveis** neste A/B sem reprocessar OpenAI (ou versionar scores por provider).
3. **Narrative vs label (local):** LLM narrative sugeriu `recommended`, mas o backend manteve `verdict_label=evaluate` (comportamento esperado: label vem da matemática v2, não do texto).

## Caveats

- **Sample único** (um candidato × uma JD); não generalizar para o produto.
- Custo e latência OpenAI **escalam** com batches de skills e tamanho de currículo + JD.
- Latência local depende de **carga GPU / Ollama** e do modelo; outro host muda o comparativo.
- Valor em USD OpenAI é estimado pela tabela do `.env`, não pela fatura em tempo real.
- Compensation Intelligence **não** entra neste baseline (permanece em Ollama, ADR-001).
- Para A/B futuros: evitar sobrescrever o score do outro provider (salvar cópia ou incluir provider no path/`id`) para conservar `final_score` / `verdict_label`.

## Onde ver métricas ao vivo

- UI **APIs Externas**: `/external-apis`
- Log append-only: `data/llm_usage.jsonl` (OpenAI)
- Por score: `audit.llm_provider`, `audit.llm_model`, `method`, `audit.usage` (OpenAI)
- API: `GET /api/llm/usage` (e resumo agregado em `GET /api/v1/external-apis/usage`)
