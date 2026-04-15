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

    async def get(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.base_url + path)
            resp.raise_for_status()
            return resp.json()

