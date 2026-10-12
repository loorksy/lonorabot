import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
from lonora_core.user_error import LonoraError


class BaseModelAdapter:
    def __init__(self, api_key: str, base_url: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.base_url = base_url
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(90, connect=15), follow_redirects=False
        )
        self.owns_client = client is None

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": "Bearer " + self.api_key, **kwargs.pop("headers", {})}
        try:
            response = await self.client.request(
                method, self.base_url + path, headers=headers, **kwargs
            )
        except httpx.HTTPError:
            raise LonoraError("model_provider_unavailable", 502) from None
        if response.status_code in {401, 403}:
            raise LonoraError("model_credentials_rejected", 502)
        if response.status_code == 429:
            raise LonoraError("model_rate_limited", 429)
        if response.status_code == 404:
            raise LonoraError("model_endpoint_unavailable", 502)
        if response.is_error:
            raise LonoraError("model_request_rejected", 502)
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError()
            return cast(dict[str, Any], value)
        except ValueError:
            raise LonoraError("model_response_invalid", 502) from None

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def stream_request(
        self, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        request_headers = {"Authorization": "Bearer " + self.api_key, **(headers or {})}
        try:
            async with self.client.stream(
                "POST", self.base_url + path, headers=request_headers, json=payload
            ) as response:
                if response.status_code in {401, 403}:
                    raise LonoraError("model_credentials_rejected", 502)
                if response.status_code == 429:
                    raise LonoraError("model_rate_limited", 429)
                if response.is_error:
                    raise LonoraError("model_request_rejected", 502)
                async for line in response.aiter_lines():
                    if len(line) > 1_000_000:
                        raise LonoraError("model_response_invalid", 502)
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    value: Any = json.loads(data)
                    if not isinstance(value, dict):
                        raise LonoraError("model_response_invalid", 502)
                    yield cast(dict[str, Any], value)
        except httpx.HTTPError:
            raise LonoraError("model_provider_unavailable", 502) from None
        except (ValueError, TypeError):
            raise LonoraError("model_response_invalid", 502) from None
