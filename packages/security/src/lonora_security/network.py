import asyncio
import hashlib
import ipaddress
import re
import socket
from urllib.parse import urlparse, urlsplit, urlunsplit

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


def endpoint_sha256(url: str) -> str:
    """Fingerprint the exact HTTPS resource, normalizing only origin spelling."""
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port not in {None, 443}
            or any(ord(char) < 33 for char in url)
        ):
            raise ValueError("unsafe endpoint")
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        canonical = urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))
    except ValueError:
        raise LonoraError("unsafe_remote_url", 422) from None
    return hashlib.sha256(canonical.encode()).hexdigest()


# An OpenAI-compatible endpoint the owner names by its base URL (mandate 12.1): the
# owner's API key goes to the owner's URL and nowhere else. The URL is checked before
# any request: http(s) only, no credentials, query or fragment in it, and plain http
# only to a host on the owner's own machine or network (a private address, or a
# one-label name such as a Compose service), so a key never crosses the internet
# unencrypted. A one-label name starts with a letter: ``134744072``, ``127.1`` and
# ``0x7f.1`` are addresses to the resolver, so they are read as addresses. The owner
# types the URL into a card an agent raised, so it never names Lonora itself: not this
# machine (loopback is Lonora's own container), not a link-local or cloud metadata
# address, and not one of Lonora's Compose services. A name is not resolved here: one
# whose DNS answer is such an address is not caught (DNS can change after any check).
SERVICE_NAME = re.compile(r"[a-z][a-z0-9-]*")
LONORA_SERVICES = frozenset(
    {"api", "browser", "caddy", "db", "gateway", "migrate", "postgres", "searxng", "workspace"}
)
METADATA_HOSTS = frozenset({"instance-data", "metadata", "metadata.google.internal"})


def _address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address a host spells, in any form the resolver reads as one."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _lonora_host(host: str) -> bool:
    if (
        host == "localhost"
        or host.endswith(".localhost")
        or host in LONORA_SERVICES
        or host in METADATA_HOSTS
    ):
        return True
    address = _address(host)
    return address is not None and (
        address.is_loopback or address.is_link_local or address.is_unspecified
    )


def _local_host(host: str) -> bool:
    address = _address(host)
    if address is not None:
        return address.is_private
    return SERVICE_NAME.fullmatch(host) is not None


def compatible_endpoint(url: str) -> str:
    """The base URL without a trailing slash, or ``unsafe_model_endpoint``."""
    value = url.strip()
    try:
        parts = urlsplit(value)
        # A trailing dot names the same host: ``localhost.`` is ``localhost``.
        host = (parts.hostname or "").lower().rstrip(".")
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
        or _lonora_host(host)
        or (parts.scheme == "http" and not _local_host(host))
        or (port is not None and not 0 < port < 65536)
    ):
        raise LonoraError("unsafe_model_endpoint", 422)
    return value.rstrip("/")
