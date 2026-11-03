"""Bounded anonymous HTTPS reads pinned to the address that passed validation.

The browser never opens a destination socket itself. Host and TLS SNI retain
the source hostname while the connection targets a validated public address.
Redirects are returned to the browser and inspected as separate requests.
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass

import httpx
from lonora_core.user_error import LonoraError


@dataclass(frozen=True)
class PublicResponse:
    status: int
    headers: dict[str, str]
    body: bytes


async def public_address(url: str) -> tuple[httpx.URL, str]:
    try:
        if len(url) > 2048:
            raise ValueError
        parsed = httpx.URL(url)
        if (
            parsed.scheme != "https"
            or not parsed.host
            or parsed.userinfo
            or parsed.port not in {None, 443}
        ):
            raise ValueError
    except (ValueError, httpx.InvalidURL):
        raise LonoraError("unsafe_remote_url", 400) from None
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, parsed.host, 443, type=socket.SOCK_STREAM
        )
    except OSError:
        raise LonoraError("remote_host_unavailable", 502) from None
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global
        or ipaddress.ip_address(address[4][0]).is_multicast
        for address in addresses
    ):
        raise LonoraError("private_remote_address_forbidden", 403)
    # Prefer IPv4 where available, without accepting an unsafe AAAA record.
    chosen = next((a for a in addresses if a[0] == socket.AF_INET), addresses[0])
    return parsed, str(chosen[4][0])


async def public_get(
    url: str, method: str = "GET", *, maximum_bytes: int = 2 * 1024 * 1024
) -> PublicResponse:
    if method not in {"GET", "HEAD"}:
        raise LonoraError("browser_request_method_forbidden", 403)
    parsed, address = await public_address(url)
    pinned = parsed.copy_with(host=address, fragment=None)
    # A client is deliberately scoped to one hostname. Pooling by the pinned IP
    # across hostnames could otherwise reuse a connection with different SNI.
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        request = client.build_request(
            method,
            pinned,
            headers={
                "Host": parsed.netloc.decode("ascii"),
                "Accept": "text/html,application/xhtml+xml,application/javascript,text/css,application/json,text/plain,*/*;q=0.5",
                "User-Agent": "LonoraResearchBrowser/1.0",
            },
            extensions={"sni_hostname": parsed.host},
        )
        response = await client.send(request, stream=True)
        try:
            size = 0
            chunks: list[bytes] = []
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > maximum_bytes:
                    raise LonoraError("research_source_too_large", 413)
                chunks.append(chunk)
            headers = {
                name: value
                for name, value in response.headers.items()
                if name.lower()
                not in {
                    "content-length",
                    "content-encoding",
                    "transfer-encoding",
                    "connection",
                    "set-cookie",
                    "www-authenticate",
                    "proxy-authenticate",
                }
            }
            return PublicResponse(response.status_code, headers, b"".join(chunks))
        finally:
            await response.aclose()
