from __future__ import annotations

from typing import Any

import httpx

from kov.config import LlmConfig


class OpenAICompatClient:
    def __init__(self, config: LlmConfig):
        self.config = config

    def _chat_completions_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        # Support both ".../v1" and base URLs without the version segment.
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"

    async def chat_completions(self, *, messages: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise RuntimeError("LLM is not configured (base_url/api_key/model)")
        url = self._chat_completions_url()
        payload: dict[str, Any] = {
            "model": overrides.get("model") or self.config.model,
            "messages": messages,
            "temperature": overrides.get("temperature", self.config.temperature),
            "max_tokens": overrides.get("max_tokens", self.config.max_tokens),
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def chat_completions_stream(
        self, *, messages: list[dict[str, Any]], **overrides: Any
    ):
        """
        Async generator yielding text deltas from OpenAI-compatible SSE stream.
        """
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise RuntimeError("LLM is not configured (base_url/api_key/model)")
        url = self._chat_completions_url()
        payload: dict[str, Any] = {
            "model": overrides.get("model") or self.config.model,
            "messages": messages,
            "temperature": overrides.get("temperature", self.config.temperature),
            "max_tokens": overrides.get("max_tokens", self.config.max_tokens),
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = httpx.Response(200, content=data).json()
                    except Exception:
                        # best-effort: ignore malformed chunks
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield str(delta)

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""
