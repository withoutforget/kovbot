from __future__ import annotations

from typing import Any

import httpx


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def post(self, path: str, json_data: Any) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url + path, json=json_data)
            resp.raise_for_status()
            return resp.json()

    async def stream_text(self, path: str, json_data: Any):
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", self.base_url + path, json=json_data) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_text():
                    if chunk:
                        yield chunk

    async def get(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.base_url + path)
            resp.raise_for_status()
            return resp.json()
