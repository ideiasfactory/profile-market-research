from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx


class LocalLLM:
    def __init__(self) -> None:
        self.url = os.getenv("LOCAL_LLM_URL", "http://gpu-server-01:11434").strip().rstrip("/")
        self.model = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:14b").strip()
        self.timeout = float(os.getenv("LOCAL_LLM_TIMEOUT", "90"))
        self.temperature = float(os.getenv("LOCAL_LLM_TEMPERATURE", "0.1"))
        self.max_parse_retries = int(os.getenv("LOCAL_LLM_PARSE_RETRIES", "2"))

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def json_completion(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
        retries: int | None = None,
    ) -> dict[str, Any] | None:
        result = await self.json_completion_with_audit(
            system,
            prompt,
            timeout=timeout,
            temperature=temperature,
            retries=retries,
        )
        return result.get("parsed") if result else None

    async def json_completion_with_audit(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
        retries: int | None = None,
    ) -> dict[str, Any] | None:
        if not self.configured:
            return None

        request_timeout = self.timeout if timeout is None else timeout
        temp = self.temperature if temperature is None else temperature
        attempts = self.max_parse_retries if retries is None else max(0, retries)
        last_raw = ""
        parse_error = ""

        for attempt in range(attempts + 1):
            retry_hint = ""
            if attempt > 0:
                retry_hint = (
                    "\n\nATENÇÃO: A resposta anterior não era JSON válido. "
                    "Responda novamente com JSON estrito apenas, sem markdown."
                )
            try:
                raw = await self._raw_completion(
                    system,
                    prompt + retry_hint,
                    timeout=request_timeout,
                    temperature=temp,
                )
            except Exception as exc:
                return {
                    "parsed": None,
                    "raw": "",
                    "model": self.model,
                    "temperature": temp,
                    "error": str(exc),
                    "attempts": attempt + 1,
                }

            last_raw = raw or ""
            parsed = _parse_json_object(last_raw)
            if isinstance(parsed, dict):
                return {
                    "parsed": parsed,
                    "raw": last_raw[:20000],
                    "model": self.model,
                    "temperature": temp,
                    "error": None,
                    "attempts": attempt + 1,
                }
            parse_error = "json_parse_failed"

        return {
            "parsed": None,
            "raw": last_raw[:20000],
            "model": self.model,
            "temperature": temp,
            "error": parse_error,
            "attempts": attempts + 1,
        }

    async def _raw_completion(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float,
        temperature: float,
    ) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if self._is_ollama_generate_url:
                response = await client.post(
                    self.generate_url,
                    json={
                        "model": self.model,
                        "prompt": f"{system}\n\n{prompt}",
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": temperature},
                    },
                )
                response.raise_for_status()
                return str(response.json().get("response", "") or "")

            response = await client.post(
                self.url,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"] or "")

    @property
    def _is_ollama_generate_url(self) -> bool:
        return "/v1/" not in self.url and not self.url.endswith("/chat/completions")

    @property
    def generate_url(self) -> str:
        if self.url.endswith("/api/generate"):
            return self.url
        return f"{self.url}/api/generate"


def _parse_json_object(content: str) -> dict[str, Any] | None:
    if not content or not str(content).strip():
        return None
    text = str(content).strip()
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        parsed = _try_load_json(candidate)
        if isinstance(parsed, dict):
            return parsed
        repaired = _repair_truncated_json(candidate)
        parsed = _try_load_json(repaired)
        if isinstance(parsed, dict):
            return parsed
    return None


def _try_load_json(content: str) -> Any | None:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _repair_truncated_json(content: str) -> str:
    """Fecha chaves/colchetes abertos e remove vírgula residual para JSON truncado."""
    text = content.strip()
    if not text.startswith("{"):
        return text
    text = re.sub(r",\s*$", "", text)
    text = re.sub(r",\s*(\"[^\"]*\"\s*:)?\s*(\"[^\"]*)?$", "", text)
    text = re.sub(r",\s*$", "", text)

    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    in_string = False
    escape = False
    for char in text:
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
    if in_string:
        text += '"'
    text += "]" * max(0, open_brackets)
    text += "}" * max(0, open_braces)
    return text
