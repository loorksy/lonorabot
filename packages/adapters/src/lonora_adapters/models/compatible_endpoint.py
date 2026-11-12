"""An OpenAI-compatible endpoint the owner names by its base URL (12.1).

The owner's API key goes to the owner's URL and nowhere else. The URL is checked
before any request: http(s) only, no credentials, query or fragment in it, and plain
http only to a host on the owner's own machine or network (loopback, a private
address, or a one-label name such as a Compose service), so a key never crosses
the internet unencrypted.
"""

import ipaddress
from urllib.parse import urlsplit

import httpx
from lonora_core.user_error import LonoraError

from .openai_compatible import OpenAICompatibleAdapter


def _local_host(host: str) -> bool:
    if host == "localhost" or ("." not in host and ":" not in host):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def compatible_endpoint(url: str) -> str:
    """The base URL without a trailing slash, or ``unsafe_model_endpoint``."""
    value = url.strip()
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        raise LonoraError("unsafe_model_endpoint", 422) from None
    if (
        parts.scheme not in {"https", "http"}
        or not host
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or any(ord(char) < 33 for char in value)
        or (parts.scheme == "http" and not _local_host(host))
        or (port is not None and not 0 < port < 65536)
    ):
        raise LonoraError("unsafe_model_endpoint", 422)
    return value.rstrip("/")


class CompatibleEndpointAdapter(OpenAICompatibleAdapter):
    provider = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, compatible_endpoint(base_url), client)
