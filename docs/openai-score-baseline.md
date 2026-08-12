# Baseline de custo e comparativo — Local vs OpenAI (LLM paga)

Baseline de planejamento/custo para uso do provider OpenAI (`gpt-4.1`) no produto, mais **comparativos honestos** versus LLM local (`qwen2.5:14b`):

1. **Score** (`score_candidate`) — A/B de latência/método/custo (**v2** Local vs OpenAI; **três eixos** incluindo OpenAI **v3**)
2. **Análise de vaga** (`analyse_job`) — A/B de rubrica (tiers/pesos) na mesma JD

Após smoke tests PO (2026-08-12).

## Métrica de negócio (OpenAI)

| Operação | Baseline de negócio (API) | Sample medido |
| --- | --- | --- |
| **Score** (`score_candidate`, v2) | **US$ 0.04 / avaliação** | ~US$ 0.037–0.038 (≈13k tokens, 4 calls) |
| **Score** (`score_candidate`, v3 + OpenAI) | **US$ 0.05 / avaliação** | ~US$ 0.046 (16 082 tokens, 5 calls incl. `score_weights`) |
| **Análise de vaga** (`analyse_job`, prompts `openai/`) | **US$ 0.03 / análise** | ~US$ 0.032 (5 907 tokens, 1 call) |

Usar esses valores para estimativas de volume, orçamento e comparação com LLM local (custo de API ≈ US$ 0; custo real = infraestrutura/GPU).

Pipeline completo típico (reanalisar JD OpenAI + score OpenAI no mesmo candidato) ≈ **US$ 0.07** no sample — **escala com nº de skills** (mais itens → mais batches de `score_skills`).

## Comparativo de negócio — quando usar cada um

| Critério | Local (`qwen2.5:14b`) | OpenAI (`gpt-4.1`) |
| --- | --- | --- |
| Custo / score (API) | **US$ 0** (só infra/GPU) | **~US$ 0.04** (baseline) |
| Custo / análise de vaga (API) | **US$ 0** | **~US$ 0.03** (baseline) |
| Latência score (sample A/B) | **~2,3–2,6 min** (task completa) | **~17 s** só nas 4 chamadas LLM; task completa tipicamente ≪ local |
| Qualidade de método no score (sample) | `hybrid` (1/2 batches de skills não usable → fallback heurístico) | `llm` (todos os batches de skills OK) |
| Rubrica da JD (sample A/B) | Enxuta (~14 itens), pesos “de faixa” v2 | Rica/discriminativa (~62 itens), pesos v3; risco de atomização |
| Privacidade / dados | Currículo/JD permanecem on-prem | Dados enviados à API OpenAI |
| Quando preferir | Volume alto, dados sensíveis, custo zero de API, GPU disponível, rubrica curada | Smoke de qualidade, baixa latência, batches LLM estáveis, sugestão de pesos/tiers, validação vs local |

**Leitura de negócio (samples 2026-08-12):** OpenAI é ~**8–9× mais rápido** no trecho LLM do score e ~**US$ 0.04** por score; na análise de vaga entrega pesos/tiers mais calibrados, mas **não deve ser usado cru como rubrica final de score** sem poda humana (ver parecer abaixo).

## Metering de usage (OpenAI + Local)

Ambos os providers gravam em `data/llm_usage.jsonl` (`provider=openai|local`).

| Provider | Fonte de tokens | `estimated_cost_usd` |
| --- | --- | --- |
| OpenAI | `usage` da Chat Completions | Tabela `OPENAI_PRICE_*` / modelo |
| Local (Ollama) | `prompt_eval_count` + `eval_count` (generate) ou `usage` (endpoint compat) | **US$ 0** por padrão (on-prem); opcional `LOCAL_LLM_PRICE_*_PER_1M` |

Resumo: `GET /api/llm/usage` (agregado) e UI **APIs Externas** (cards OpenAI + Local). Scores persistem `audit.usage` para qualquer provider quando há tokens.

## Sample técnico OpenAI — score (referência de custo)

| Campo | Valor |
| --- | --- |
| Data | 2026-08-12 (~15:23 local / 18:23 UTC) — smoke inicial |
| Provider / modelo | `openai` / `gpt-4.1` |
| Método | `llm` |
| Chamadas API | 4 (`score_skills` ×2, `score_fit`, `score_narrative`) |
| Tokens | ~11 030 prompt / 1 971 completion / 13 001 total |
| Custo estimado (tabela env) | ~US$ 0.038 → baseline de negócio **US$ 0.04** |
| Wall das 4 calls | ~16,6 s (`llm_usage.jsonl` 18:23:17 → 18:23:33 UTC) |

Preços usados no metering: `OPENAI_PRICE_INPUT_PER_1M` / `OPENAI_PRICE_OUTPUT_PER_1M` (defaults documentados no README).

Nota: `score_skills` aparece **2×** quando há >12 skills (`SCORE_BATCH_SIZE=12`); não é retry — são lotes.

## Comparativo controlado A/B — score v2 (mesmo par, só troca provider)

Controle limpo (2026-08-12 ~16:57–17:01 local / 19:57–20:01 UTC): **mesma vaga, mesmo candidato, `scoring_model=v2`**, só `llm_provider` muda. Histórico de score preserva ambos os runs.

Par: **Bruno Libanio** · `job_id=671bb12e8d6c` · `candidate_id=e475d1052f49` · scoring **v2**.

| Campo | OpenAI (`…T195811Z_openai`) | Local (atual / `20:01`) |
| --- | --- | --- |
| `llm_provider` | `openai` | `local` |
| Modelo | `gpt-4.1` | `qwen2.5:14b` |
| `scoring_model_version` | **v2** | **v2** |
| `method` | `llm` | `hybrid` |
| `final_score` | **59.47** | **54.9** |
| `verdict_label` | **evaluate** | **evaluate** |
| Δ score | — | OpenAI **+4.57** vs local |
| Tokens / custo API | 12 999 · **~US$ 0.038** (4 calls) | 9 934 · **US$ 0** (3 calls OK + 1 batch skills sem tokens / falha parcial) |
| Latência task | ~23 s (queued→completed) | ~**186 s** |
| Dimensões | core 45.4 · role 80 · context **95** · behavioral 88 · diff 0 | core 44.2 · role 75 · context 80 · behavioral 80 · diff 0 |

### Divergências de skill (mesmo critério v2)

| Skill | Local | OpenAI |
| --- | --- | --- |
| Arquitetura de Integração | 3 | **5** |
| API Management | 4 | **5** |
| Comunicação | null | **4** |
| Liderança Técnica | 4 | **5** |
| Oracle Integration Cloud | **4** | 3 |
| SAP Process Orchestration | **3** | 2 |

Gaps em 0 iguais: EIP, SAP BTP, Observabilidade, OpenAPI, Kafka, TOGAF, ArchiMate.

### Parecer sincero (controle v2)

1. **Veredito idêntico (`evaluate`)** — engines concordam no gate de negócio; OpenAI só é ~5 pts mais alto.
2. **OpenAI não “infla tudo”** — no âncora OIC foi **mais duro** (3 vs 4); o lift vem sobretudo de Arquitetura/API/soft + role/context fit.
3. **Local continua `hybrid`** — pelo menos um batch de `score_skills` sem tokens úteis / fallback; isso sozinho enviesa o A/B e reforça OpenAI em estabilidade de pipeline.
4. **Custo vs latência** — OpenAI ~US$ 0.04 e ~8× mais rápido neste sample; local 0 API com ~3 min e tokens agora mensuráveis (~10k/run).
5. **Conclusão operacional:** para smoke de qualidade e latência, OpenAI no score v2 é justificável; para volume/privacidade, local permanece viável se aceitar `hybrid` ocasional e latência de GPU.

Smoke anterior (~15:23) tinha perdido o JSON OpenAI por sobrescrita; com histórico isso não se repete.

## Comparativo em três eixos — Local v2 × OpenAI v2 × OpenAI v3

Mesmo profissional e mesma vaga (rubrica persistida da vaga local enxuta): **Bruno Libanio** · `job_id=671bb12e8d6c` · `candidate_id=e475d1052f49`.

O terceiro eixo isola o efeito do **`scoring_model=v3`** (recalibração de pesos via LLM no score time) em cima do motor OpenAI já medido no v2 — sem misturar com a rubrica expandida da vaga `3c53e6963cc9`.

| Eixo | Local v2 (atual) | OpenAI v2 (`…T195811Z`) | OpenAI v3 (`…T194301Z`) |
| --- | --- | --- | --- |
| Provider | `local` | `openai` | `openai` |
| Modelo LLM | `qwen2.5:14b` | `gpt-4.1` | `gpt-4.1` |
| `scoring_model` | **v2** | **v2** | **v3** (+ `score_weights`) |
| `method` | `hybrid` | `llm` | `llm` |
| `final_score` | **54.9** | **59.47** | **60.16** |
| `verdict_label` | `evaluate` | `evaluate` | `evaluate` |
| Δ vs Local v2 | — | **+4.57** | **+5.26** |
| Δ vs OpenAI v2 | — | — | **+0.69** |
| Must-have | 1/1 (OIC) | 1/1 (OIC) | **2/2** (OIC + Arquitetura) |
| core / role / context / behavioral | 44.2 / 75 / 80 / 80 | 45.4 / 80 / **95** / 88 | **46.7** / 80 / **95** / **89.1** |
| Tokens · custo API | 9 934 · US$ 0 (3 calls) | 12 915 · ~**US$ 0.037** (4 calls) | 16 082 · ~**US$ 0.046** (5 calls) |
| Extra vs v2 OpenAI | — | — | `score_weights` ~3.1k tokens · ~US$ 0.009 |

### Skills-chave nos três eixos

| Skill | Local v2 (tier/w → score) | OpenAI v2 | OpenAI v3 |
| --- | --- | --- | --- |
| Oracle Integration Cloud | MUST/10 → **4** | MUST/10 → **3** | MUST/10 → **3** |
| Arquitetura de Integração | CORE/7 → **3** | CORE/7 → **5** | **MUST/9 → 5** (promovida no v3) |
| API Management | CORE/6 → 4 | CORE/6 → **5** | CORE/6 → **5** |
| Comunicação | SOFT/3 → null | SOFT/3 → **4** | SOFT/**6** → **4** |
| Liderança Técnica | SOFT/2 → 4 | SOFT/2 → **5** | SOFT/**5** → **5** |
| SAP Process Orchestration | CORE/7 → **3** | CORE/7 → **2** | CORE/**8** → **2** |

Recalibração v3 (audit `weight_policy`): além de Arquitetura→MUST/9, subiu pesos de softs (Comunicação 3→6, Liderança 2→5), Observabilidade 3→5, Kafka 2→4, SAP PO 7→8; baixou EIP 6→5. A vaga no disco **não** foi alterada — só o score.

### Parecer sincero (três eixos)

1. **Gate estável:** os três fecham em `evaluate`. Nenhum eixo muda a decisão de “avançar / não avançar” neste sample.
2. **Eixo provider (Local v2 → OpenAI v2):** +4.6 pts — motor + estabilidade `llm` vs `hybrid`; OpenAI mais generoso em arquitetura/API/soft e em context_fit; mais duro em OIC/SAP PO.
3. **Eixo modelo de score (OpenAI v2 → OpenAI v3):** só **+0.7 pt**. Os scores 0–5 das skills âncora quase não mudam (OIC=3, Arquitetura=5, API=5); o ganho vem da **política de pesos** (Arquitetura vira must-have com peso 9; softs mais pesados; behavioral 88→89).
4. **Custo marginal do v3:** ~**+US$ 0.009** (~US$ 0.037 → ~US$ 0.046) por uma call `score_weights`. Barato em relação ao salto Local→OpenAI, mas o retorno em score neste candidato foi pequeno.
5. **Leitura de produto:** para este par, **OpenAI v2 já captura quase todo o ganho** vs local; v3 é refinamento de rubrica no score-time, útil quando se quer pesos mais discriminativos **sem** editar a vaga — não um “salto de qualidade” do juiz de skills.
6. **Caveat:** o run v3 (~19:43 UTC) é ~15 min anterior ao v2 OpenAI controlado; skills OpenAI batem de forma consistente entre os dois, então o Δ v2→v3 é atribuível sobretudo aos pesos, não a uma mudança grosseira de evidência.

**Recomendação de uso (este sample):** default de score OpenAI em **v2**; usar **v3** quando o PO quiser experimentar recalibração de pesos sem tocar nos critérios salvos — e sempre inspecionar `audit.weight_policy` (before/after).

## Parecer A/B — análise de vaga Local vs OpenAI (2026-08-12)

Mesma JD base (**Arquiteto OIC - CPFL**), duas vagas persistidas para A/B:

| Lado | `job_id` | Título | Provider / prompts |
| --- | --- | --- | --- |
| Local | `671bb12e8d6c` (`/jobs/671bb12e8d6c`) | Arquiteto OIC - CPFL | Análise antiga (sem `llm_provider`/`audit` no JSON) · `weight_policy=v2` |
| OpenAI | `3c53e6963cc9` (`/jobs/3c53e6963cc9`) | Arquiteto OIC - CPFL (OpenAI) | `openai` / `gpt-4.1` · `prompt_set=openai` · `weight_policy=v3` · `analyzed_at` 19:29 UTC |

### Sample técnico OpenAI — analyse_job

| Campo | Valor |
| --- | --- |
| Data | 2026-08-12 (~16:29 local / 19:29 UTC) |
| Operation | `analyse_job` (1 call) |
| Tokens | 2 517 prompt / 3 390 completion / **5 907** total |
| Custo estimado | **~US$ 0.032** → baseline de negócio **US$ 0.03** / análise |
| Contagem de itens | must 6 · core 16 · supporting 16 · differentials 12 · soft 12 (**62** total — próximo do teto do prompt) |

Local (mesma JD): **14** itens (must 2 · core 4 · supporting 3 · differentials 3 · soft 2).

### O que o OpenAI fez melhor (rubrica)

1. **Pesos discriminativos** — gradação real dentro do tier (ex.: OIC=10, Arquitetura=9, Desenho=8), não só o “teto de faixa” do clamp v2.
2. **Hierarquia mais alinhada a arquiteto OIC** — eleva *Arquitetura de Integração* a **MUST_HAVE**; trata SAP PO/BTP como **SUPPORTING** (ecossistema), não CORE equivalente ao OIC (no local, SAP PO/BTP ficam CORE peso 7).
3. **Grupos semânticos e contexto** — skill groups e `context_signals` mais ricos (utilities, CPFL, transformação digital, SAP+OIC).

### Onde o OpenAI exagera (impacto direto no score)

1. **Atomização** — CORS/TLS/mTLS/JWT/OpenID como cores separados; soft skills viram ~12 atributos quase sinônimos. Infla a superfície de avaliação e aumenta risco de falso negativo no score.
2. **Encheu o schema até o limite** — sinal de “extrair o máximo” mais do que “curar o essencial”.
3. **Custo composto** — rubrica com ~62 skills ⇒ mais batches de `score_skills` no score OpenAI (custo/latência sobem além do baseline de US$ 0.04 medido com a rubrica local enxuta).

### O que o local fez melhor (ou mais útil operacionalmente)

1. **Rubrica usável** — ~14 itens dá para o recrutador validar e o score interpretar sem ruído.
2. **Foco** — OIC + arquitetura + bloco SAP + poucos diferenciais; mais próximo de must vs nice humano.
3. **Menos risco de score “duro por granularidade”**.

### Divergências que mudam o score (mesmo candidato)

- Arquitetura de Integração: OpenAI **MUST/9** vs Local **CORE/7** → mexe em must-have coverage.
- OpenAPI / OAuth: OpenAI sobe a **CORE**; local deixa **SUPPORTING**.
- SAP PO / BTP: Local **CORE/7**; OpenAI **SUPPORTING/4** — quem é forte em SAP e médio em OIC (e vice-versa) muda de perfil.
- Soft: 2 itens locais vs 12 comportamentais OpenAI → `behavioral_fit` vira outro jogo.

### Veredito de negócio (análise de vaga)

| Uso | Recomendação |
| --- | --- |
| Entendimento / sugestão de pesos e tiers | **OpenAI** (melhor calibração e hierarquia OIC-first) |
| Rubrica final para score em produção | **Local curado** ou **OpenAI + poda humana** (reduzir must-haves a 3–5, fundir softs, não isolar TLS/CORS como itens) |
| OpenAI cru como critério de score | **Não** — ótimo rascunho máximo, não critério final estável |

Próximo experimento recomendado: **mesmo candidato** nas duas vagas (`671bb12e8d6c` vs `3c53e6963cc9`) com o mesmo `llm_provider` no score, para medir delta numérico de `final_score` / `verdict_label` / must-have coverage / custo (esperado: OpenAI-rubrica mais cara e potencialmente mais punitiva).

## Caveats

- **Samples únicos** (um candidato × uma JD no score; um par de análises na mesma JD); não generalizar para o produto.
- Custo e latência OpenAI **escalam** com batches de skills e tamanho de currículo + JD.
- Latência local depende de **carga GPU / Ollama** e do modelo; outro host muda o comparativo.
- Valor em USD OpenAI é estimado pela tabela do `.env`, não pela fatura em tempo real.
- Compensation Intelligence **não** entra neste baseline (permanece em Ollama, ADR-001).
- Para A/B futuros de score: o histórico de score já evita sobrescrever o outro provider; reprocessar arquiva o run anterior.
- Para A/B de análise de vaga: preferir **clonar vaga** (`POST /jobs/{id}/clone`) e reanalisar com outro `llm_provider`, em vez de sobrescrever a análise original.

## Onde ver métricas ao vivo

- UI **APIs Externas**: `/external-apis` (cards OpenAI + Local)
- Log append-only: `data/llm_usage.jsonl` (`provider=openai|local`)
- Por score: `audit.llm_provider`, `audit.llm_model`, `method`, `audit.usage`
- Por análise de vaga: `analysis.llm_provider`, `analysis.prompt_set`, `analysis.weight_policy`, `analysis.audit.usage`
- API: `GET /api/llm/usage` (e resumo agregado em `GET /api/v1/external-apis/usage`)

## Histórico de score (Local vs OpenAI)

Reprocessar o mesmo par **arquiva** o detalhe anterior em `data/scores/history/` e no índice `data/score_history.json`; o arquivo/índice “atual” (`job_id_candidate_id`) continua apontando para o último run.

Assim o A/B Local vs OpenAI **não perde** `final_score` / `verdict_label` / custo do run anterior. Na UI **Scores**, abra o par e use a tabela **Histórico de execuções** (link *abrir* em cada run). Na API, `GET /api/gpt/evaluations/{id}?include_history=true` lista arquivos; ids históricos também resolvem em `GET /api/gpt/evaluations/{history_id}`.

Gráfico multi-score lado a lado na UI fica em backlog (BL-003).
