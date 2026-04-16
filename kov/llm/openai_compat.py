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

    @staticmethod
    def _use_max_completion_tokens(model: str) -> bool:
        """
        Some OpenAI-compatible providers/models (notably GPT-5 / o-series) use `max_completion_tokens`
        instead of `max_tokens` in Chat Completions.
        """
        m = (model or "").strip().lower()
        return m.startswith("gpt-5") or m.startswith("o")

    @staticmethod
    def _supports_custom_temperature(model: str) -> bool:
        """
        Some providers/models only support the default temperature (often 1.0) and
        reject any explicit `temperature` parameter.
        """
        m = (model or "").strip().lower()
        # Proxy/OpenAI-compatible GPT-5 family often enforces default-only temperature.
        return not (m.startswith("gpt-5") or m.startswith("o"))

    @classmethod
    def _build_payload(cls, *, model: str, messages: list[dict[str, Any]], overrides: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages}

        temperature = overrides.get("temperature", overrides.get("_default_temperature"))
        # If the model/provider doesn't support custom temperature, omit it and let server default apply.
        if temperature is not None and cls._supports_custom_temperature(model):
            payload["temperature"] = temperature

        max_tokens = overrides.get("max_tokens", overrides.get("_default_max_tokens"))
        max_completion_tokens = overrides.get("max_completion_tokens")

        if cls._use_max_completion_tokens(model):
            payload["max_completion_tokens"] = max_completion_tokens if max_completion_tokens is not None else max_tokens
        else:
            payload["max_tokens"] = max_tokens
        return payload

    @staticmethod
    def _looks_like_max_tokens_error(e: Exception) -> bool:
        msg = str(e) or ""
        resp_text = ""
        if isinstance(e, httpx.HTTPStatusError):
            try:
                resp_text = e.response.text or ""
            except Exception:
                resp_text = ""
        hay = msg + "\n" + resp_text
        return "Unsupported parameter" in hay and "max_tokens" in hay and "max_completion_tokens" in hay

    @staticmethod
    def _looks_like_temperature_error(e: Exception) -> bool:
        msg = str(e) or ""
        resp_text = ""
        if isinstance(e, httpx.HTTPStatusError):
            try:
                resp_text = e.response.text or ""
            except Exception:
                resp_text = ""
        hay = msg + "\n" + resp_text
        return "temperature" in hay and "Only the default" in hay and "unsupported" in hay.lower()

    @staticmethod
    def _looks_like_stream_options_error(e: Exception) -> bool:
        msg = str(e) or ""
        resp_text = ""
        if isinstance(e, httpx.HTTPStatusError):
            try:
                resp_text = e.response.text or ""
            except Exception:
                resp_text = ""
        hay = (msg + "\n" + resp_text).lower()
        return "stream_options" in hay and ("unsupported" in hay or "unknown" in hay or "invalid" in hay)

    async def chat_completions(self, *, messages: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise RuntimeError("LLM is not configured (base_url/api_key/model)")
        url = self._chat_completions_url()
        model = overrides.get("model") or self.config.model
        payload = self._build_payload(
            model=model,
            messages=messages,
            overrides={
                **overrides,
                "_default_temperature": self.config.temperature,
                "_default_max_tokens": self.config.max_tokens,
            },
        )
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if (
                    not self.extract_text(data).strip()
                    and self.config.fallback_model
                    and (model or "").strip() != self.config.fallback_model.strip()
                ):
                    payload_fb = dict(payload)
                    payload_fb["model"] = self.config.fallback_model.strip()
                    resp_fb = await client.post(url, json=payload_fb, headers=headers)
                    resp_fb.raise_for_status()
                    return resp_fb.json()
                return data
            except httpx.HTTPStatusError as e:
                # Best-effort retry for providers/models that require max_completion_tokens.
                if self._looks_like_max_tokens_error(e) and "max_tokens" in payload and "max_completion_tokens" not in payload:
                    payload2 = dict(payload)
                    payload2["max_completion_tokens"] = payload2.pop("max_tokens")
                    resp2 = await client.post(url, json=payload2, headers=headers)
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    if (
                        not self.extract_text(data2).strip()
                        and self.config.fallback_model
                        and (model or "").strip() != self.config.fallback_model.strip()
                    ):
                        payload_fb = dict(payload2)
                        payload_fb["model"] = self.config.fallback_model.strip()
                        resp_fb = await client.post(url, json=payload_fb, headers=headers)
                        resp_fb.raise_for_status()
                        return resp_fb.json()
                    return data2
                # Best-effort retry for providers/models that reject explicit temperature.
                if self._looks_like_temperature_error(e) and "temperature" in payload:
                    payload2 = dict(payload)
                    payload2.pop("temperature", None)
                    resp2 = await client.post(url, json=payload2, headers=headers)
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    if (
                        not self.extract_text(data2).strip()
                        and self.config.fallback_model
                        and (model or "").strip() != self.config.fallback_model.strip()
                    ):
                        payload_fb = dict(payload2)
                        payload_fb["model"] = self.config.fallback_model.strip()
                        resp_fb = await client.post(url, json=payload_fb, headers=headers)
                        resp_fb.raise_for_status()
                        return resp_fb.json()
                    return data2
                raise

    async def chat_completions_stream(
        self, *, messages: list[dict[str, Any]], **overrides: Any
    ):
        """
        Async generator yielding text deltas from OpenAI-compatible SSE stream.
        """
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise RuntimeError("LLM is not configured (base_url/api_key/model)")
        url = self._chat_completions_url()
        model = overrides.get("model") or self.config.model
        payload = self._build_payload(
            model=model,
            messages=messages,
            overrides={
                **overrides,
                "_default_temperature": self.config.temperature,
                "_default_max_tokens": self.config.max_tokens,
            },
        )
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        headers = {"Authorization": f"Bearer {self.config.api_key}"}

        usage_out: dict[str, int] | None = overrides.get("usage_out")
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                stream_ctx = client.stream("POST", url, json=payload, headers=headers)
                resp_cm = stream_ctx
            except Exception:
                raise

            try:
                async with resp_cm as resp:
                    resp.raise_for_status()
                    content_type = (resp.headers.get("content-type") or "").lower()
                    if "text/event-stream" not in content_type:
                        # Provider ignored `stream=true` and returned a normal JSON response.
                        body = await resp.aread()
                        try:
                            parsed = httpx.Response(200, content=body).json()
                            text = self.extract_text(parsed).strip()
                            if not text and self.config.fallback_model and model.strip() != self.config.fallback_model.strip():
                                fb = await self.chat_completions(messages=messages, model=self.config.fallback_model.strip())
                                text = self.extract_text(fb).strip()
                                if usage_out is not None:
                                    usage = self.extract_usage(fb)
                                    if usage:
                                        usage_out.clear()
                                        usage_out.update(usage)
                            if text:
                                if usage_out is not None:
                                    usage = self.extract_usage(parsed)
                                    if usage:
                                        usage_out.clear()
                                        usage_out.update(usage)
                                yield text
                            return
                        except Exception:
                            # Fall back to raw body as text (best-effort).
                            raw_text = body.decode("utf-8", errors="ignore").strip()
                            if raw_text:
                                yield raw_text
                            return
                    emitted = False
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            # Some providers may stream plain JSON without SSE framing.
                            try:
                                parsed = httpx.Response(200, content=line).json()
                                text = self.extract_text(parsed).strip()
                                if text:
                                    if usage_out is not None:
                                        usage = self.extract_usage(parsed)
                                        if usage:
                                            usage_out.clear()
                                            usage_out.update(usage)
                                    yield text
                                    return
                            except Exception:
                                continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = httpx.Response(200, content=data).json()
                        except Exception:
                            # best-effort: ignore malformed chunks
                            continue
                        if usage_out is not None:
                            u = chunk.get("usage") if isinstance(chunk, dict) else None
                            if isinstance(u, dict):
                                pt = int(u.get("prompt_tokens") or 0)
                                ct = int(u.get("completion_tokens") or 0)
                                tt = int(u.get("total_tokens") or (pt + ct))
                                usage_out.clear()
                                usage_out.update(
                                    {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}
                                )
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content")
                        if delta:
                            yield str(delta)
                            emitted = True

                    # If the provider returned a valid stream but never emitted content, retry with fallback model.
                    if not emitted and self.config.fallback_model and model.strip() != self.config.fallback_model.strip():
                        fb = await self.chat_completions(messages=messages, model=self.config.fallback_model.strip())
                        text = self.extract_text(fb).strip()
                        if text:
                            if usage_out is not None:
                                usage = self.extract_usage(fb)
                                if usage:
                                    usage_out.clear()
                                    usage_out.update(usage)
                            yield text
            except httpx.HTTPStatusError as e:
                # Retry once swapping max_tokens -> max_completion_tokens
                if self._looks_like_max_tokens_error(e) and "max_tokens" in payload and "max_completion_tokens" not in payload:
                    payload2 = dict(payload)
                    payload2["max_completion_tokens"] = payload2.pop("max_tokens")
                    async with client.stream("POST", url, json=payload2, headers=headers) as resp2:
                        resp2.raise_for_status()
                        async for line in resp2.aiter_lines():
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
                                continue
                            if usage_out is not None:
                                u = chunk.get("usage") if isinstance(chunk, dict) else None
                                if isinstance(u, dict):
                                    pt = int(u.get("prompt_tokens") or 0)
                                    ct = int(u.get("completion_tokens") or 0)
                                    tt = int(u.get("total_tokens") or (pt + ct))
                                    usage_out.clear()
                                    usage_out.update(
                                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}
                                    )
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = (choices[0].get("delta") or {}).get("content")
                            if delta:
                                yield str(delta)
                    return
                # Retry once dropping temperature to let server default apply.
                if self._looks_like_temperature_error(e) and "temperature" in payload:
                    payload2 = dict(payload)
                    payload2.pop("temperature", None)
                    async with client.stream("POST", url, json=payload2, headers=headers) as resp2:
                        resp2.raise_for_status()
                        async for line in resp2.aiter_lines():
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
                                continue
                            if usage_out is not None:
                                u = chunk.get("usage") if isinstance(chunk, dict) else None
                                if isinstance(u, dict):
                                    pt = int(u.get("prompt_tokens") or 0)
                                    ct = int(u.get("completion_tokens") or 0)
                                    tt = int(u.get("total_tokens") or (pt + ct))
                                    usage_out.clear()
                                    usage_out.update(
                                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}
                                    )
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = (choices[0].get("delta") or {}).get("content")
                            if delta:
                                yield str(delta)
                    return
                # Retry once dropping stream_options for providers that don't support it.
                if self._looks_like_stream_options_error(e) and "stream_options" in payload:
                    payload2 = dict(payload)
                    payload2.pop("stream_options", None)
                    async with client.stream("POST", url, json=payload2, headers=headers) as resp2:
                        resp2.raise_for_status()
                        content_type = (resp2.headers.get("content-type") or "").lower()
                        if "text/event-stream" not in content_type:
                            body = await resp2.aread()
                            try:
                                parsed = httpx.Response(200, content=body).json()
                                text = self.extract_text(parsed)
                                if text:
                                    if usage_out is not None:
                                        usage = self.extract_usage(parsed)
                                        if usage:
                                            usage_out.clear()
                                            usage_out.update(usage)
                                    yield text
                                return
                            except Exception:
                                raw_text = body.decode("utf-8", errors="ignore").strip()
                                if raw_text:
                                    yield raw_text
                                return
                        async for line in resp2.aiter_lines():
                            if not line:
                                continue
                            if not line.startswith("data:"):
                                try:
                                    parsed = httpx.Response(200, content=line).json()
                                    text = self.extract_text(parsed)
                                    if text:
                                        if usage_out is not None:
                                            usage = self.extract_usage(parsed)
                                            if usage:
                                                usage_out.clear()
                                                usage_out.update(usage)
                                        yield text
                                        return
                                except Exception:
                                    continue
                            data = line[len("data:") :].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = httpx.Response(200, content=data).json()
                            except Exception:
                                continue
                            if usage_out is not None:
                                u = chunk.get("usage") if isinstance(chunk, dict) else None
                                if isinstance(u, dict):
                                    pt = int(u.get("prompt_tokens") or 0)
                                    ct = int(u.get("completion_tokens") or 0)
                                    tt = int(u.get("total_tokens") or (pt + ct))
                                    usage_out.clear()
                                    usage_out.update(
                                        {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}
                                    )
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = (choices[0].get("delta") or {}).get("content")
                            if delta:
                                yield str(delta)
                    return
                raise

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""

    @staticmethod
    def extract_usage(response: dict[str, Any]) -> dict[str, int] | None:
        usage = response.get("usage") if isinstance(response, dict) else None
        if not isinstance(usage, dict):
            return None
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
