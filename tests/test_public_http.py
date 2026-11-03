"""The browser reader validates and pins every actual outbound connection."""

import gzip
import socket
from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from lonora_core.user_error import LonoraError
from lonora_security.public_http import public_address, public_get


def address(value: str) -> tuple[Any, ...]:
    family = socket.AF_INET6 if ":" in value else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (value, 443))


def mock_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    original = httpx.AsyncClient

    def create(**options: Any) -> httpx.AsyncClient:
        assert options["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **options)

    return create


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "file:///etc/passwd",
        "data:text/html,example",
        "https://user:secret@example.com/",
        "https://example.com:8443/",
        "https://example.com:wrong/",
        "not a URL",
    ],
)
@pytest.mark.asyncio
async def test_unsafe_url_is_rejected_before_dns(url: str) -> None:
    with patch("lonora_security.public_http.socket.getaddrinfo") as dns:
        with pytest.raises(LonoraError, match="unsafe_remote_url"):
            await public_address(url)
        dns.assert_not_called()


@pytest.mark.parametrize(
    "destination",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
        "ff02::1",
    ],
)
@pytest.mark.asyncio
async def test_nonpublic_and_multicast_dns_destinations_are_forbidden(destination: str) -> None:
    with patch(
        "lonora_security.public_http.socket.getaddrinfo", return_value=[address(destination)]
    ):
        with pytest.raises(LonoraError, match="private_remote_address_forbidden"):
            await public_address("https://example.com/")


@pytest.mark.asyncio
async def test_mixed_dns_records_are_rejected_even_with_a_public_ipv4() -> None:
    with patch(
        "lonora_security.public_http.socket.getaddrinfo",
        return_value=[address("1.1.1.1"), address("::1")],
    ):
        with pytest.raises(LonoraError, match="private_remote_address_forbidden"):
            await public_address("https://example.com/")


@pytest.mark.asyncio
async def test_dns_failures_and_empty_answers_have_explicit_errors() -> None:
    with patch("lonora_security.public_http.socket.getaddrinfo", side_effect=socket.gaierror):
        with pytest.raises(LonoraError, match="remote_host_unavailable"):
            await public_address("https://example.com/")
    with patch("lonora_security.public_http.socket.getaddrinfo", return_value=[]):
        with pytest.raises(LonoraError, match="private_remote_address_forbidden"):
            await public_address("https://example.com/")


@pytest.mark.asyncio
async def test_connection_targets_validated_ip_while_host_and_tls_keep_original_identity() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://1.1.1.1/document?q=value"
        assert request.headers["Host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers
        return httpx.Response(
            302,
            content=b"redirect",
            headers={
                "location": "https://127.0.0.1/private",
                "set-cookie": "session=not-shared",
                "www-authenticate": "Basic",
                "proxy-authenticate": "Basic",
                "connection": "keep-alive",
                "content-type": "text/plain",
            },
        )

    with (
        patch(
            "lonora_security.public_http.socket.getaddrinfo",
            return_value=[address("2606:4700:4700::1111"), address("1.1.1.1")],
        ) as dns,
        patch("lonora_security.public_http.httpx.AsyncClient", side_effect=mock_client(respond)),
    ):
        result = await public_get("https://example.com/document?q=value#fragment")
    assert len(requests) == 1 and dns.call_count == 1
    assert result.status == 302
    assert result.body == b"redirect"
    assert result.headers == {
        "location": "https://127.0.0.1/private",
        "content-type": "text/plain",
    }


@pytest.mark.asyncio
async def test_each_public_read_revalidates_dns_and_does_not_reuse_prior_cookie_state() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "1.1.1.1"
        assert "cookie" not in request.headers
        return httpx.Response(200, content=b"public", headers={"set-cookie": "session=x"})

    with (
        patch(
            "lonora_security.public_http.socket.getaddrinfo",
            side_effect=[[address("1.1.1.1")], [address("127.0.0.1")]],
        ) as dns,
        patch("lonora_security.public_http.httpx.AsyncClient", side_effect=mock_client(respond)),
    ):
        await public_get("https://example.com/first")
        with pytest.raises(LonoraError, match="private_remote_address_forbidden"):
            await public_get("https://example.com/second")
    assert dns.call_count == 2


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_response_limit_applies_after_decompression_and_closes_rejected_stream() -> None:
    stream = Chunks([gzip.compress(b"x" * 10000)])

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, headers={"content-encoding": "gzip"})

    with (
        patch("lonora_security.public_http.socket.getaddrinfo", return_value=[address("1.1.1.1")]),
        patch("lonora_security.public_http.httpx.AsyncClient", side_effect=mock_client(respond)),
    ):
        with pytest.raises(LonoraError, match="research_source_too_large"):
            await public_get("https://example.com/large", maximum_bytes=100)
    assert stream.closed


@pytest.mark.asyncio
async def test_nonread_methods_are_rejected_before_dns_or_network() -> None:
    with patch("lonora_security.public_http.socket.getaddrinfo") as dns:
        with pytest.raises(LonoraError, match="browser_request_method_forbidden"):
            await public_get("https://example.com/", "POST")
        dns.assert_not_called()
