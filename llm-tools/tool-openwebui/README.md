# Open WebUI × Professional Profile Analyser

Pacote em `llm-tools/tool-openwebui/` para usar o **Open WebUI** como frontend conversacional do PPA, com tools apontando para `/api/gpt/*`.

## Arquitetura

```text
User
  ↓
Open WebUI  (chat + OpenAPI Tool Server  —ou—  tool Python)
  ↓  Bearer / X-API-Key (opcional)
Professional Profile Analyser  /api/gpt/*
  ↓
Ollama (gpu-server-01:11434)   ← LLM do chat e/ou do PPA
```

## Pré-requisitos

1. PPA rodando (ex.: `uvicorn app.main:app --reload` → `http://127.0.0.1:8000`).
2. Ollama acessível (modo A ou B abaixo).
3. Em ambientes não locais, `PROFESSIONAL_PROFILE_API_KEY` no `.env` da raiz do PPA (nunca commitar `.env`).

## Ollama: dois modos

Containers Docker **não** herdam o DNS/hosts do Mac. O compose mapeia `gpu-server-01` via `extra_hosts` e usa `host.docker.internal` para serviços no host.

### Modo A — Ollama remoto (GPU lab) — padrão

```bash
ping -c 2 gpu-server-01
curl -sS http://gpu-server-01:11434/api/tags

cp llm-tools/tool-openwebui/.env.example llm-tools/tool-openwebui/.env
# edite: GPU_SERVER_IP=<lan-ip>  OLLAMA_BASE_URL=http://gpu-server-01:11434
```

`GPU_SERVER_IP` (ou `OLLAMA_HOST_IP`) é **obrigatório** para o `extra_hosts`. Sem isso o default vira `127.0.0.1` dentro do container.

```bash
docker exec ppa-open-webui getent hosts gpu-server-01
docker exec ppa-open-webui curl -sS http://gpu-server-01:11434/api/tags
```

### Modo B — Ollama no Mac / Docker host

```bash
# em llm-tools/tool-openwebui/.env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

```bash
docker exec ppa-open-webui curl -sS http://host.docker.internal:11434/api/tags
```

---

## 1) Subir / recrear Open WebUI (Docker)

A partir da **raiz do repositório**:

```bash
cp llm-tools/tool-openwebui/.env.example llm-tools/tool-openwebui/.env
# preencha GPU_SERVER_IP (modo A) se necessário

docker compose \
  --env-file llm-tools/tool-openwebui/.env \
  -f llm-tools/tool-openwebui/docker-compose.open-webui.yml \
  up -d --force-recreate
```

Logs / follow (o `-f` do *compose file* vai **antes** do subcomando; `logs -f` = follow):

```bash
docker compose \
  -f llm-tools/tool-openwebui/docker-compose.open-webui.yml \
  logs -f
```

`--env-file` também é opção **global** (antes do subcomando). Ex.: `docker compose --env-file ... -f ... up`, nunca `docker compose logs --env-file ...`.

Alternativa (CWD carrega `.env` automaticamente):

```bash
cd llm-tools/tool-openwebui
docker compose -f docker-compose.open-webui.yml up -d --force-recreate
```

Abra: **http://127.0.0.1:3000** (ou `OPEN_WEBUI_PORT`).

Na primeira subida (volume novo) o container pode ficar alguns minutos sem responder enquanto baixa o modelo de embeddings do Hugging Face — `Connection reset` / “Connection Failed” é esperado até o healthcheck ficar `healthy`.

| Variável | Uso |
|----------|-----|
| `GPU_SERVER_IP` | IP LAN de `gpu-server-01` (modo A) |
| `OLLAMA_HOST_IP` | Alias se `GPU_SERVER_IP` não estiver setado |
| `OLLAMA_BASE_URL` | Default `http://gpu-server-01:11434`; modo B: `http://host.docker.internal:11434` |
| `OPEN_WEBUI_PORT` | Porta no host (default `3000`) |
| `PPA_BASE_URL` | Docs / Server URL das tools (`http://host.docker.internal:8000`) |
| `WEBUI_AUTH` | Opcional; auth do próprio Open WebUI |

Não use o `.env` de secrets da raiz do projeto para substituição do compose — use `llm-tools/tool-openwebui/.env`.

---

## 2) Como criar as tools (duas opções)

### A) Global Tool Server (OpenAPI) — **preferido**

**Não use** Espaço de Trabalho → Ferramentas para o JSON OpenAPI. Essa tela espera **Python** (`{"id","name","content"}`). Importar `openapi.slim.json` lá falha em silêncio.

| Onde (UI PT-BR) | Quem busca o OpenAPI | Base URL |
|-----------------|----------------------|----------|
| **Configurações → Admin → Integrações** (Global Tool Server) | **Container** | `http://host.docker.internal:8000` |
| **Configurações → Integrações** (Pessoal / User Tool Server) | **Browser** | `http://127.0.0.1:8000` |

#### Passos manuais (Global — Docker)

1. Confirme o PPA e o OpenAPI:

```bash
curl -sS http://127.0.0.1:8000/openapi-gpt-slim.json | head -c 120
docker exec ppa-open-webui curl -sS -o /dev/null -w "%{http_code}\n" \
  http://host.docker.internal:8000/openapi-gpt-slim.json
# esperado: 200  (127.0.0.1:8000 de dentro do container falha)
```

2. Abra **http://127.0.0.1:3000**.
3. Menu do usuário → **Configurações**.
4. Coluna **Admin** → **Integrações** (não a Integrações “Pessoal”, a menos que queira User Tool Server).
5. Em **Ferramentas → Servidores de Ferramentas Externas** → **＋**.
6. Preencha:

| Campo | Valor |
|-------|--------|
| **URL** | `http://host.docker.internal:8000` |
| **Path** | `openapi-gpt-slim.json` (não o default `openapi.json`) |
| **Type** | OpenAPI |
| **Auth** | `none` (local sem API key) · ou Bearer / `X-API-Key` se `PROFESSIONAL_PROFILE_API_KEY` estiver setada |
| **Enable** | on |

7. **Verify** (se existir) → **Salvar**.
8. Opcional: cole o system prompt de [`system-prompt.md`](./system-prompt.md) nas instruções do modelo / chat.

Arquivos locais úteis para revisão (o import é por URL, não upload):

| Arquivo | Uso |
|---------|-----|
| [`openapi.slim.3.0.json`](./openapi.slim.3.0.json) | OpenAPI 3.0.3 canônico |
| [`openapi.slim.yaml`](./openapi.slim.yaml) | Fonte editável |
| `http://127.0.0.1:8000/openapi-gpt-slim.json` | Spec servido pelo PPA |

Após editar o YAML:

```bash
python -c "import json,yaml; from pathlib import Path; p=Path('llm-tools/tool-openwebui'); data=yaml.safe_load(p.joinpath('openapi.slim.yaml').read_text()); text=json.dumps(data, ensure_ascii=False, indent=2)+'\n'; p.joinpath('openapi.slim.json').write_text(text); p.joinpath('openapi.slim.3.0.json').write_text(text); Path('app/static/openapi-gpt-slim.json').write_text(text)"
```

### B) Tool Python manual — fallback (Espaço de Trabalho → Ferramentas)

Use se o import OpenAPI falhar ou se preferir Valves configuráveis no Workspace.

1. Abra **http://127.0.0.1:3000**.
2. **Espaço de Trabalho → Ferramentas** → criar / importar.
3. Cole o conteúdo de [`tools/ppa_tools.py`](./tools/ppa_tools.py) (classe `Tools` + `Valves`).
4. Salve e configure **Valves**:
   - `ppa_base_url`: `http://host.docker.internal:8000` (Open WebUI em Docker) **ou** `http://127.0.0.1:8000` (Open WebUI no host)
   - `api_key`: vazio localmente; senão a mesma `PROFESSIONAL_PROFILE_API_KEY`
   - `timeout_seconds`: `120` (ou mais para `research_compensation_wait`)
5. No chat, habilite a ferramenta **Professional Profile Analyser**.

Métodos principais: `list_jobs`, `get_job`, `list_candidates`, `evaluate_candidate`, `get_task`, `prefill_compensation_from_job`, `research_compensation_wait`, `research_compensation_async`.

---

## 3) Como testar (passo a passo)

### Preparar

1. PPA up: `uvicorn app.main:app --reload` → `http://127.0.0.1:8000`.
2. Recreate Open WebUI (comandos da seção 1).
3. Configure tools (A ou B acima).
4. (Opcional) Cole [`system-prompt.md`](./system-prompt.md).

### Habilitar tools no chat

1. Abra um chat em **http://127.0.0.1:3000**.
2. Botão **Integrações** (no composer / barra do chat) → **Ferramentas**.
3. Ligue **Professional Profile Analyser** (OpenAPI `server:ppa` ou a tool Python).
4. Envie um prompt de smoke:

```text
Liste as vagas cadastradas no Professional Profile Analyser e mostre id + título.
Não invente dados — use a tool listJobs / list_jobs.
```

Esperado: citation/tool call com vagas reais (ex.: `server:ppa/listJobs`).

### Smoke remuneração (cache)

```text
Para a vaga <nome ou id>, faça prefill de compensação e pesquise a faixa de mercado.
Use cache (force_refresh false). Não invente salários.
```

Ou direto:

```text
Pesquise remuneração PJ para o perfil "Engenheiro de Integração Oracle OIC",
remoto, Brasil, usando researchCompensationWait / research_compensation_wait
com force_refresh false.
```

Só use `force_refresh: true` se o usuário pedir explicitamente (“ignore o cache”, “force refresh”, etc.).

### Checklist rápido

- [ ] PPA em `:8000`
- [ ] Modo A: `GPU_SERVER_IP` no `.env` desta pasta; curl Ollama **dentro** do container OK
- [ ] Tool Server via **Configurações → Admin → Integrações** (não Workspace → Ferramentas para OpenAPI)
- [ ] URL Global: `http://host.docker.internal:8000` · Path `openapi-gpt-slim.json` · Auth `none`
- [ ] Chat: Integrações → Ferramentas → ligar PPA
- [ ] Smoke: listar jobs → prefill → wait research **sem** force_refresh

---

## Gotchas

| Sintoma | Causa / correção |
|---------|------------------|
| Import OpenAPI “não faz nada” | Você está em **Espaço de Trabalho → Ferramentas** (só Python). Use **Configurações → Admin → Integrações**. |
| Global Tool Server não alcança PPA | URL `http://127.0.0.1:8000` **dentro do container** aponta para o próprio container. Use `http://host.docker.internal:8000`. |
| User Tool Server (Pessoal) | O **browser** busca o OpenAPI → use `http://127.0.0.1:8000`. CORS: `CORS_ALLOW_ORIGINS` inclui `http://127.0.0.1:3000`. |
| Path `openapi.json` | Importa o FastAPI completo (rotas HTML). Use `openapi-gpt-slim.json`. |
| Chat sem GPU | `GPU_SERVER_IP` vazio → `extra_hosts` cai em `127.0.0.1`. |
| 401 nas tools | Alinhe Auth Bearer / API key com `PROFESSIONAL_PROFILE_API_KEY` do PPA. |
| Salários inventados | System prompt + política de cache; cite só `market` / `sources` / `observations` / `warnings`. |

### API alternativa (se a UI falhar)

Com sessão admin (`localStorage.token`):

```bash
# Verify
POST /api/v1/configs/tool_servers/verify
# Persist (substitui a lista inteira — preserve conexões existentes)
POST /api/v1/configs/tool_servers
# Body exemplo:
# {"TOOL_SERVER_CONNECTIONS":[{
#   "url":"http://host.docker.internal:8000",
#   "path":"openapi-gpt-slim.json",
#   "type":"openapi",
#   "auth_type":"none",
#   "key":"",
#   "config":{"enable":true},
#   "info":{"id":"ppa","name":"Professional Profile Analyser"}
# }]}
```

---

## Política de cache (obrigatória)

| Comportamento | Quando |
|---------------|--------|
| `force_refresh: false` (padrão) | Sempre, inclusive pesquisas “normais” |
| `force_refresh: true` | Só se o usuário pedir explicitamente ignorar cache |

Preferência de tool para remuneração:

1. `researchCompensationWait` / `research_compensation_wait`
2. `researchCompensationAsync` + `getTask`
3. `researchCompensation` (legado / smoke)

Não aponte tools para `/api/v1/compensation/*` (UI HTML). Use sempre `/api/gpt/*`.

---

## Artefatos

| Arquivo | Conteúdo |
|---------|----------|
| `openapi.slim.3.0.json` / `.json` / `.yaml` | Spec slim OpenAPI |
| `http://…:8000/openapi-gpt-slim.json` | Rota PPA para import por URL |
| `app/static/openapi-gpt-slim.json` | Espelho estático |
| `system-prompt.md` | Instruções do modelo (PT-BR) |
| `docker-compose.open-webui.yml` | Overlay Open WebUI |
| `.env.example` | Template de env (não commitar `.env`) |
| `tools/ppa_tools.py` | Tool Python para Workspace → Ferramentas |
| `../../docs/adr/ADR-016-*.md` | ADR Open WebUI + cache-default |

Ver também: [`../custom-gpt/`](../custom-gpt/) (Custom GPT), README principal do repositório.
