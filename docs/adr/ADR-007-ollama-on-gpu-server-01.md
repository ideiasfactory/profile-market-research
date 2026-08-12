# ADR-007 — Ollama on gpu-server-01

Decision: v1 uses Ollama at `http://gpu-server-01:11434` with default model `qwen2.5:14b`.

Reason: LLM execution is isolated from the API host and remains internal.
