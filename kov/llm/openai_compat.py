from __future__ import annotations

from typing import Any

import httpx

from kov.config import LlmConfig


class OpenAICompatClient:
    def __init__(self, config: LlmConfig):
        self.config = config

    async def chat_completions(self, *, messages: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise RuntimeError("LLM is not configured (base_url/api_key/model)")
        url = self.config.base_url.rstrip("/") + "/v1/chat/completions"
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

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""

