# ADR-018 — Inject Business Parameters into LLM Prompts

## Status

Accepted

## Context

Parâmetros de negócio (margem, impostos, políticas, fatores de conversão, etc.) precisam influenciar análises e respostas da LLM sem hardcode nos arquivos de prompt nem republicação de artefatos a cada ajuste. Os prompts já vivem externalizados em `prompts/` e são carregados via `app.prompts.load_prompt`.

## Decision

1. `load_prompt` mescla automaticamente placeholders vindos do catálogo de negócio (`prompt_placeholders()`), com precedência para kwargs explícitos da chamada.
2. Placeholders disponíveis quando `inject_in_prompts=true`:
   - `{<key>}` — valor individual (ex.: `{target_margin_pct}`, `{clt_to_pj_factor}`)
   - `{business_context}` — bloco textual com label, chave, valor e descrição
3. Placeholders ausentes no template permanecem literais (`_SafeDict`); prompts existentes com `{{` escapado para JSON de exemplo continuam válidos.
4. Parâmetros com `inject_in_prompts=false` não entram no contexto dos prompts (podem ainda ser usados por código Python).

## Consequences

- Operadores editam regras na UI `/settings` e o próximo `load_prompt` já reflete os valores.
- Autores de prompt optam por embutir `{business_context}` ou chaves específicas; nada é forçado em todos os templates.
- Colisão de nomes: kwargs da chamada vencem parâmetros de negócio.
- Mudanças de parâmetros não invalidam cache de arquivos de prompt (`lru_cache` só no texto-fonte); o format é runtime.
