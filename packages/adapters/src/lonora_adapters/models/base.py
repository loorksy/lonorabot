import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
from lonora_adapter_kit.model_errors import (
    REFUSAL_STOPS,
    TRUNCATION_STOPS,
    FailureReason,
    ModelProviderError,
    classify_failure,
    response_failure,
)

# Error bodies are small; never buffer an unbounded one to classify it.
ERROR_BODY_LIMIT = 65536


def transport_failure(error: httpx.HTTPError) -> ModelProviderError:
    reason = (
        FailureReason.TIMEOUT
        if isinstance(error, httpx.TimeoutException)
        else FailureReason.CONNECTION
    )
    return ModelProviderError(reason, provider_type=type(error).__name__)


def invalid_response() -> ModelProviderError:
    return ModelProviderError(FailureReason.INVALID_RESPONSE)


def interrupted_stream() -> ModelProviderError:
    """The stream closed before the provider's end-of-message marker."""
    return ModelProviderError(FailureReason.CONNECTION, provider_type="stream_incomplete")


def stream_error(value: dict[str, Any]) -> ModelProviderError:
    """An error event inside an otherwise successful stream."""
    return classify_failure(None, value)


def stopped_reply(stop_reason: Any, text: str, has_calls: bool) -> dict[str, Any]:
    """Apply the provider's stop reason before any tool input is trusted.

    A refusal withholds the answer. A reply cut off at the output budget never
    yields tool calls, whose input may be incomplete; the router retries with
    a larger budget instead. A cut-off text answer is kept and flagged.
    """
    if stop_reason in REFUSAL_STOPS:
        raise ModelProviderError(FailureReason.CONTENT_POLICY, provider_type=str(stop_reason))
    if stop_reason in TRUNCATION_STOPS:
        if has_calls or not text:
            raise ModelProviderError(FailureReason.TRUNCATED, provider_type=str(stop_reason))
        return {"stop_reason": stop_reason, "output_truncated": True}
    return {"stop_reason": stop_reason}


# The model ended its own turn: Anthropic's end_turn and stop_sequence, OpenAI's stop.
FINISHED_STOPS = frozenset({"end_turn", "stop_sequence", "stop"})


def chosen_silence(allow_empty: bool, stop_reason: Any) -> bool:
    """A reply with no text and no call is the model's own choice only where the caller
    allows one (a background run, VISION 11.5) and the model ended its turn; a turn that
    ended for calls it does not carry, or with a gateway's error, is a broken response."""
    return allow_empty and stop_reason in FINISHED_STOPS


class BaseModelAdapter:
    def __init__(self, api_key: str, base_url: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.base_url = base_url
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(90, connect=15), follow_redirects=False
        )
        self.owns_client = client is None

    def auth_headers(self) -> dict[str, str]:
        """The API key in the header the provider documents for API keys."""
        return {"Authorization": "Bearer " + self.api_key}

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {**self.auth_headers(), **kwargs.pop("headers", {})}
        try:
            response = await self.client.request(
                method, self.base_url + path, headers=headers, **kwargs
            )
        except httpx.HTTPError as error:
            raise transport_failure(error) from None
        if not 200 <= response.status_code < 300:
            raise response_failure(
                response.status_code, response.content[:ERROR_BODY_LIMIT], response.headers
            )
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError()
            return cast(dict[str, Any], value)
        except ValueError:
            raise invalid_response() from None

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def stream_request(
        self, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        request_headers = {**self.auth_headers(), **(headers or {})}
        try:
            async with self.client.stream(
                "POST", self.base_url + path, headers=request_headers, json=payload
            ) as response:
                if not 200 <= response.status_code < 300:
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) >= ERROR_BODY_LIMIT:
                            break
                    raise response_failure(
                        response.status_code, body[:ERROR_BODY_LIMIT], response.headers
                    )
                async for line in response.aiter_lines():
                    if len(line) > 1_000_000:
                        raise invalid_response()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    value: Any = json.loads(data)
                    if not isinstance(value, dict):
                        raise invalid_response()
                    yield cast(dict[str, Any], value)
        except httpx.HTTPError as error:
            raise transport_failure(error) from None
        except (ValueError, TypeError):
            raise invalid_response() from None
