import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from lonora_core.user_error import LonoraError


async def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.port not in {None, 443}
    ):
        raise LonoraError("unsafe_remote_url")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, 443, type=socket.SOCK_STREAM
        )
    except OSError:
        raise LonoraError("remote_host_unavailable", 502) from None
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global for address in addresses
    ):
        raise LonoraError("private_remote_address_forbidden", 403)
    return url


def trusted_provider_url(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username:
        raise LonoraError("untrusted_provider_url", 403)
    return url
