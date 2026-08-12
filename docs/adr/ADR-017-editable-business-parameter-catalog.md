# ADR-017 — Editable Business Parameter Catalog (JSON)

## Status

Accepted

## Context

O produto precisa de regras de negócio configuráveis (conversão CLT↔PJ, horas/mês, impostos, margem, políticas comerciais, etc.). A primeira abordagem considerou um formulário fixo só para impostos/margem/preço de venda. Isso acoplava o schema da UI a um caso de uso específico e não escalava para outros parâmetros.

Já existiam fatores de conversão em `.env` (`CLT_TO_PJ_FACTOR`, `WORK_HOURS_MONTH`), úteis para ops, mas inadequados para edição frequente por negócio via UI.

## Decision

1. Manter um **catálogo genérico** de parâmetros em `data/business_settings.json`, gerenciado por `app/business_settings.py`.
2. Cada parâmetro tem: `id`, `key` (snake_case), `label`, `value`, `value_type` (`number` | `percent` | `text` | `boolean`), `category`, `description`, `inject_in_prompts`.
3. Expor CRUD na UI (`GET/POST /settings`, create/delete de parâmetros) e na API (`GET/PUT /api/v1/settings/business`, upsert/delete de itens).
4. Seeds iniciais (ISS, PIS/COFINS, overhead, margem, fator CLT→PJ, horas/mês) são **exemplos**; o operador pode incluir, alterar ou remover qualquer chave.
5. Chaves conhecidas (`clt_to_pj_factor`, `work_hours_month`) alimentam `CompensationSettings` quando presentes; `.env` permanece fallback de bootstrap.

## Consequences

- Regras de negócio evoluem sem deploy de código/schema rígido.
- A UI de gestão não assume um modelo tributário único.
- Código que consome parâmetros deve ler por `key` (mapa `values`) e tolerar ausência.
- Persistência continua file-backed (JSON), alinhada ao MVP; migração futura para DB é possível sem mudar o contrato conceitual do catálogo.
