from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol, runtime_checkable

import httpx


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "local").strip().lower()
if LLM_PROVIDER not in {"local", "openai"}:
    LLM_PROVIDER = "local"


def active_llm_provider(override: str | None = None) -> str:
    if override and override.strip().lower() in {"local", "openai"}:
        return override.strip().lower()
    value = (os.getenv("LLM_PROVIDER") or LLM_PROVIDER or "local").strip().lower()
    if value not in {"local", "openai"}:
        return "local"
    return value


@runtime_checkable
class LLMClient(Protocol):
    configured: bool
    provider_name: str
    model: str
    timeout: float
    temperature: float

    async def json_completion(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
        retries: int | None = None,
        operation: str | None = None,
        job_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any] | None: ...

    async def json_completion_with_audit(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
        retries: int | None = None,
        operation: str | None = None,
        job_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any] | None: ...


class LocalLLM:
    provider_name = "local"

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
        operation: str | None = None,
        job_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any] | None:
        result = await self.json_completion_with_audit(
            system,
            prompt,
            timeout=timeout,
            temperature=temperature,
            retries=retries,
            operation=operation,
            job_id=job_id,
            candidate_id=candidate_id,
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
        operation: str | None = None,
        job_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.configured:
            return None

        from app.llm_usage import estimate_cost_usd, record_usage_event

        request_timeout = self.timeout if timeout is None else timeout
        temp = self.temperature if temperature is None else temperature
        attempts = self.max_parse_retries if retries is None else max(0, retries)
        last_raw = ""
        parse_error = ""
        last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        for attempt in range(attempts + 1):
            retry_hint = ""
            if attempt > 0:
                retry_hint = (
                    "\n\nATENÇÃO: A resposta anterior não era JSON válido. "
                    "Responda novamente com JSON estrito apenas, sem markdown."
                )
            try:
                raw, usage = await self._raw_completion(
                    system,
                    prompt + retry_hint,
                    timeout=request_timeout,
                    temperature=temp,
                )
            except Exception as exc:
                record_usage_event(
                    provider=self.provider_name,
                    model=self.model,
                    operation=operation or "unknown",
                    job_id=job_id,
                    candidate_id=candidate_id,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    estimated_cost_usd=0.0,
                    attempts=attempt + 1,
                    ok=False,
                )
                return {
                    "parsed": None,
                    "raw": "",
                    "model": self.model,
                    "provider": self.provider_name,
                    "temperature": temp,
                    "error": str(exc),
                    "attempts": attempt + 1,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                }

            last_usage = usage
            last_raw = raw or ""
            parsed = _parse_json_object(last_raw)
            if isinstance(parsed, dict):
                cost = estimate_cost_usd(
                    self.model,
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                    provider=self.provider_name,
                )
                record_usage_event(
                    provider=self.provider_name,
                    model=self.model,
                    operation=operation or "unknown",
                    job_id=job_id,
                    candidate_id=candidate_id,
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                    total_tokens=usage["total_tokens"],
                    estimated_cost_usd=cost,
                    attempts=attempt + 1,
                    ok=True,
                )
                return {
                    "parsed": parsed,
                    "raw": last_raw[:20000],
                    "model": self.model,
                    "provider": self.provider_name,
                    "temperature": temp,
                    "error": None,
                    "attempts": attempt + 1,
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"],
                    "estimated_cost_usd": cost,
                }
            parse_error = "json_parse_failed"

        cost = estimate_cost_usd(
            self.model,
            last_usage["prompt_tokens"],
            last_usage["completion_tokens"],
            provider=self.provider_name,
        )
        record_usage_event(
            provider=self.provider_name,
            model=self.model,
            operation=operation or "unknown",
            job_id=job_id,
            candidate_id=candidate_id,
            prompt_tokens=last_usage["prompt_tokens"],
            completion_tokens=last_usage["completion_tokens"],
            total_tokens=last_usage["total_tokens"],
            estimated_cost_usd=cost,
            attempts=attempts + 1,
            ok=False,
        )
        return {
            "parsed": None,
            "raw": last_raw[:20000],
            "model": self.model,
            "provider": self.provider_name,
            "temperature": temp,
            "error": parse_error,
            "attempts": attempts + 1,
            "prompt_tokens": last_usage["prompt_tokens"],
            "completion_tokens": last_usage["completion_tokens"],
            "total_tokens": last_usage["total_tokens"],
            "estimated_cost_usd": cost,
        }

    async def _raw_completion(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float,
        temperature: float,
    ) -> tuple[str, dict[str, int]]:
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
                data = response.json()
                content = str(data.get("response", "") or "")
                prompt_tokens = int(data.get("prompt_eval_count") or 0)
                completion_tokens = int(data.get("eval_count") or 0)
                total_tokens = prompt_tokens + completion_tokens
                return content, {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }

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
            data = response.json()
            content = str(data["choices"][0]["message"]["content"] or "")
            usage_raw = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            prompt_tokens = int(usage_raw.get("prompt_tokens") or 0)
            completion_tokens = int(usage_raw.get("completion_tokens") or 0)
            total_tokens = int(usage_raw.get("total_tokens") or (prompt_tokens + completion_tokens))
            return content, {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }

    @property
    def _is_ollama_generate_url(self) -> bool:
        return "/v1/" not in self.url and not self.url.endswith("/chat/completions")

    @property
    def generate_url(self) -> str:
        if self.url.endswith("/api/generate"):
            return self.url
        return f"{self.url}/api/generate"


class OpenAILLM:
    provider_name = "openai"

    def __init__(self) -> None:
        self.api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        self.base_url = (
            os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).strip().rstrip("/")
        self.model = (os.getenv("OPENAI_MODEL") or "gpt-4.1").strip() or "gpt-4.1"
        self.timeout = _env_float("OPENAI_TIMEOUT", 90.0)
        self.temperature = _env_float("OPENAI_TEMPERATURE", 0.1)
        self.max_parse_retries = int(os.getenv("OPENAI_PARSE_RETRIES", os.getenv("LOCAL_LLM_PARSE_RETRIES", "2")))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    async def json_completion(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
        retries: int | None = None,
        operation: str | None = None,
        job_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any] | None:
        result = await self.json_completion_with_audit(
            system,
            prompt,
            timeout=timeout,
            temperature=temperature,
            retries=retries,
            operation=operation,
            job_id=job_id,
            candidate_id=candidate_id,
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
        operation: str | None = None,
        job_id: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.configured:
            return None

        from app.llm_usage import estimate_cost_usd, record_usage_event

        request_timeout = self.timeout if timeout is None else timeout
        temp = self.temperature if temperature is None else temperature
        attempts = self.max_parse_retries if retries is None else max(0, retries)
        last_raw = ""
        parse_error = ""
        last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        for attempt in range(attempts + 1):
            retry_hint = ""
            if attempt > 0:
                retry_hint = (
                    "\n\nATENÇÃO: A resposta anterior não era JSON válido. "
                    "Responda novamente com JSON estrito apenas, sem markdown."
                )
            try:
                raw, usage = await self._raw_completion(
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
                    "provider": self.provider_name,
                    "temperature": temp,
                    "error": str(exc),
                    "attempts": attempt + 1,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                }

            last_raw = raw or ""
            last_usage = usage
            cost = estimate_cost_usd(
                self.model,
                usage["prompt_tokens"],
                usage["completion_tokens"],
            )
            parsed = _parse_json_object(last_raw)
            if isinstance(parsed, dict):
                payload = {
                    "parsed": parsed,
                    "raw": last_raw[:20000],
                    "model": self.model,
                    "provider": self.provider_name,
                    "temperature": temp,
                    "error": None,
                    "attempts": attempt + 1,
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"],
                    "estimated_cost_usd": cost,
                }
                record_usage_event(
                    provider=self.provider_name,
                    model=self.model,
                    operation=operation or "unknown",
                    job_id=job_id,
                    candidate_id=candidate_id,
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                    total_tokens=usage["total_tokens"],
                    estimated_cost_usd=cost,
                    attempts=attempt + 1,
                    ok=True,
                )
                return payload
            parse_error = "json_parse_failed"

        cost = estimate_cost_usd(
            self.model,
            last_usage["prompt_tokens"],
            last_usage["completion_tokens"],
        )
        record_usage_event(
            provider=self.provider_name,
            model=self.model,
            operation=operation or "unknown",
            job_id=job_id,
            candidate_id=candidate_id,
            prompt_tokens=last_usage["prompt_tokens"],
            completion_tokens=last_usage["completion_tokens"],
            total_tokens=last_usage["total_tokens"],
            estimated_cost_usd=cost,
            attempts=attempts + 1,
            ok=False,
        )
        return {
            "parsed": None,
            "raw": last_raw[:20000],
            "model": self.model,
            "provider": self.provider_name,
            "temperature": temp,
            "error": parse_error,
            "attempts": attempts + 1,
            "prompt_tokens": last_usage["prompt_tokens"],
            "completion_tokens": last_usage["completion_tokens"],
            "total_tokens": last_usage["total_tokens"],
            "estimated_cost_usd": cost,
        }

    async def _raw_completion(
        self,
        system: str,
        prompt: str,
        *,
        timeout: float,
        temperature: float,
    ) -> tuple[str, dict[str, int]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.chat_url,
                headers=headers,
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
            data = response.json()
        content = ""
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = str(message.get("content") or "")
        usage_raw = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        prompt_tokens = int(usage_raw.get("prompt_tokens") or 0)
        completion_tokens = int(usage_raw.get("completion_tokens") or 0)
        total_tokens = int(usage_raw.get("total_tokens") or (prompt_tokens + completion_tokens))
        return content, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }


def get_llm(provider: str | None = None) -> LocalLLM | OpenAILLM:
    resolved = active_llm_provider(provider)
    if resolved == "openai":
        return OpenAILLM()
    return LocalLLM()


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
