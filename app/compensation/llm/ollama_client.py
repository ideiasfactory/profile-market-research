from __future__ import annotations

import os

from app.llm import LocalLLM


def compensation_llm() -> LocalLLM:
    os.environ.setdefault("LOCAL_LLM_URL", os.getenv("OLLAMA_BASE_URL", "http://gpu-server-01:11434"))
    os.environ.setdefault("LOCAL_LLM_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5:14b"))
    os.environ.setdefault("LOCAL_LLM_TEMPERATURE", "0.1")
    return LocalLLM()
