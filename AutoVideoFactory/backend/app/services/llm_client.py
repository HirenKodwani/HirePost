from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx

from ..core.config import settings
from ..core.exceptions import AIClientError, AIClientRateLimitError
from ..core.logging import get_logger

logger = get_logger("autovideofactory.services.llm")


class LLMClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        ...

    @abstractmethod
    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        ...


class OllamaClient(LLMClient):
    def __init__(self, base_url: str = "", model: str = "") -> None:
        self._base_url = base_url or settings.ollama_base_url
        self._model = model or settings.ollama_default_model
        self._http = httpx.AsyncClient(timeout=600.0)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        try:
            payload = {
                "model": kwargs.get("model", self._model),
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", settings.llm_temperature),
                    "num_predict": kwargs.get("max_tokens", settings.llm_max_tokens),
                },
            }
            if system_prompt:
                payload["system"] = system_prompt

            response = await self._http.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise AIClientRateLimitError(retry_after=30) from e
            raise AIClientError(f"Ollama request failed: {e}") from e
        except Exception as e:
            raise AIClientError(f"Ollama error: {e}") from e

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        json_prompt = f"{prompt}\n\nRespond ONLY with valid JSON. No markdown, no code fences, no explanation."
        result = await self.generate(json_prompt, system_prompt, **kwargs)
        return self._parse_json_response(result)

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        import json as json_lib
        import re
        cleaned = text.strip()
        for prefix in ["```json", "```", "`"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
            if cleaned.endswith(prefix):
                cleaned = cleaned[:-len(prefix)]
        cleaned = cleaned.strip()
        try:
            return json_lib.loads(cleaned)
        except json_lib.JSONDecodeError:
            match = re.search(r"\{[^{}]*(\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json_lib.loads(match.group())
                except json_lib.JSONDecodeError:
                    pass
            raise AIClientError(f"Failed to parse JSON from LLM response: {text[:200]}")


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "") -> None:
        self._api_key = api_key or settings.openai_api_key or ""
        self._base_url = base_url or settings.openai_base_url or "https://api.openai.com/v1"
        self._model = model or settings.openai_default_model
        self._http = httpx.AsyncClient(timeout=120.0)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        import asyncio
        max_retries = kwargs.pop("max_retries", 5)
        for attempt in range(max_retries):
            try:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": kwargs.get("model", self._model),
                    "messages": messages,
                    "temperature": kwargs.get("temperature", settings.llm_temperature),
                    "max_tokens": kwargs.get("max_tokens", settings.llm_max_tokens),
                }
                if "response_format" in kwargs:
                    payload["response_format"] = kwargs["response_format"]

                response = await self._http.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = min(2 ** attempt * 5, 120)
                    logger.warning(f"Rate limited (attempt {attempt+1}/{max_retries}), retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                raise AIClientError(f"OpenAI request failed: {e}") from e
            except Exception as e:
                raise AIClientError(f"OpenAI error: {e}") from e
        raise AIClientError("Max retries exceeded for OpenAI request")

    async def generate_json(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        result = await self.generate(
            prompt, system_prompt or "You are a helpful assistant that outputs valid JSON only.",
            response_format={"type": "json_object"},
            **kwargs
        )
        import json as json_lib
        try:
            return json_lib.loads(result.strip())
        except json_lib.JSONDecodeError:
            raise AIClientError(f"Failed to parse JSON: {result[:200]}")


def get_llm_client() -> LLMClient:
    if settings.llm_provider.value == "openai":
        return OpenAIClient()
    return OllamaClient()
