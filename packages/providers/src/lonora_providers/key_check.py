"""A typed model key, checked without reading the provider's model list (VISION 12.4).

``GET {base}/models`` with the key, before it is saved: a 2xx answer accepts the key, and
any other answer fails as a model request would (401 and 403 reject the key). Only the
status is read, and an error body to classify it; what the provider lists is never kept,
because Lonora's list is the one it ships. The owner's own endpoint is the exception: its
models are read (``discovery``).
"""

import httpx
from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError, response_failure
from lonora_adapters.models.base import ERROR_BODY_LIMIT, BaseModelAdapter, transport_failure

# The answers that reject the key itself; anything else could not check it.
REJECTED = frozenset({401, 403})


async def check_key(adapter: ModelAdapter) -> None:
    """Return when the provider accepts the adapter's key; raise its failure otherwise."""
    if not isinstance(adapter, BaseModelAdapter):
        raise ModelProviderError(FailureReason.UNKNOWN, provider_type="no_key_check")
    try:
        async with adapter.client.stream(
            "GET", adapter.base_url + "/models", headers=adapter.auth_headers()
        ) as response:
            if 200 <= response.status_code < 300:
                return
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) >= ERROR_BODY_LIMIT:
                    break
    except httpx.HTTPError as error:
        raise transport_failure(error) from None
    raise response_failure(response.status_code, body[:ERROR_BODY_LIMIT], response.headers)
