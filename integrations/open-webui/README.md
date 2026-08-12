# Moved

Este pacote foi movido para [`llm-tools/tool-openwebui/`](../../llm-tools/tool-openwebui/).

Use:

```bash
# a partir da raiz do repositório
docker compose \
  --env-file llm-tools/tool-openwebui/.env \
  -f llm-tools/tool-openwebui/docker-compose.open-webui.yml \
  up -d --force-recreate
```

Guia completo (setup + testes): [`llm-tools/tool-openwebui/README.md`](../../llm-tools/tool-openwebui/README.md).
