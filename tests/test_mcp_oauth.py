"""Signing in to a remote MCP server: the OAuth 2.1 client with PKCE (VISION.md 13.1).

The protocol half of ``lonora_adapters.mcp.oauth``: the server's sign-in challenge,
discovery (RFC 9728, then RFC 8414 or OpenID metadata), dynamic client registration
(RFC 7591), PKCE (RFC 7636), the resource indicator (RFC 8707), the code exchange, the
refresh, and the callback's issuer (RFC 9207). No network: a scripted resource server and
authorization server answer through httpx's MockTransport.
"""

import asyncio
import base64
import gzip
import hashlib
import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from lonora_adapters.mcp import oauth
from lonora_core.user_error import LonoraError

SERVER = "https://mcp.example.test/mcp"
ISSUER = "https://auth.example.test"
CALLBACK = "https://lonora.example.test/api/mcp/oauth/callback"
PRM = "https://mcp.example.test/.well-known/oauth-protected-resource/mcp"
PRM_ROOT = "https://mcp.example.test/.well-known/oauth-protected-resource"
AS_METADATA = ISSUER + "/.well-known/oauth-authorization-server"
Answer = httpx.Response | Callable[[httpx.Request], httpx.Response]


def authorization_server(**changes: Any) -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "registration_endpoint": ISSUER + "/register",
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        **changes,
    }


def protected_resource(**changes: Any) -> dict[str, Any]:
    return {"resource": SERVER, "authorization_servers": [ISSUER], **changes}


class Remote:
    """The resource and authorization servers, scripted by method and address."""

    def __init__(self, answers: dict[tuple[str, str], Answer]):
        self.answers = answers
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.get((request.method, str(request.url.copy_with(query=None))))
        if answer is None:
            return httpx.Response(404)
        return answer(request) if callable(answer) else answer

    @property
    def visited(self) -> list[str]:
        return [f"{item.method} {item.url.copy_with(query=None)}" for item in self.requests]


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[tuple[str, str], Answer]], Remote]:
    async def public(url: str) -> str:
        return url

    monkeypatch.setattr(oauth, "validate_public_url", public)

    def install(answers: dict[tuple[str, str], Answer]) -> Remote:
        script = Remote(answers)
        monkeypatch.setattr(
            oauth,
            "http_client",
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(script)),
        )
        return script

    return install


def discovered(**changes: Any) -> dict[tuple[str, str], Answer]:
    return {
        ("GET", PRM): httpx.Response(200, json=protected_resource()),
        ("GET", AS_METADATA): httpx.Response(200, json=authorization_server(**changes)),
    }


def test_a_bearer_challenge_names_its_metadata_and_scope() -> None:
    header = (
        'Basic realm="old", Bearer realm="mcp", error="invalid_token", '
        f'resource_metadata="{PRM}", scope="files:read, files:write"'
    )
    assert oauth.bearer_challenge(header) == oauth.Challenge(
        resource_metadata=PRM, scope="files:read, files:write"
    )
    assert oauth.bearer_challenge("bearer scope=read") == oauth.Challenge(scope="read")
    assert oauth.bearer_challenge('Bearer scope="a \\"b\\""') == oauth.Challenge(scope='a "b"')
    # No header: a 401 alone asks for a sign-in. Only another scheme: no Bearer sign-in.
    assert oauth.bearer_challenge(None) == oauth.Challenge()
    assert oauth.bearer_challenge('Basic realm="x"') is None


@pytest.mark.asyncio
async def test_the_probe_asks_without_credentials_and_only_a_401_means_sign_in(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    challenge = f'Bearer resource_metadata="{PRM}"'
    script = remote(
        {("POST", SERVER): httpx.Response(401, headers={"WWW-Authenticate": challenge})}
    )
    assert await oauth.needs_sign_in(SERVER) == oauth.Challenge(resource_metadata=PRM)
    [probe] = script.requests
    assert "authorization" not in probe.headers
    assert probe.headers["MCP-Protocol-Version"] == "2025-06-18"
    assert json.loads(probe.content)["method"] == "initialize"
    for answer in (
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}),
        httpx.Response(401, headers={"WWW-Authenticate": 'Basic realm="x"'}),
        httpx.Response(403),
        httpx.Response(500),
    ):
        remote({("POST", SERVER): answer})
        assert await oauth.needs_sign_in(SERVER) is None
    remote({("POST", SERVER): httpx.Response(401)})
    assert await oauth.needs_sign_in(SERVER) == oauth.Challenge()


@pytest.mark.asyncio
async def test_discovery_reads_the_named_metadata_then_the_authorization_server(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    script = remote(discovered(authorization_response_iss_parameter_supported=True))
    plan = await oauth.discover(SERVER, oauth.Challenge(resource_metadata=PRM, scope="read"))
    assert script.visited == [f"GET {PRM}", f"GET {AS_METADATA}"]
    assert plan == oauth.SignInPlan(
        resource=SERVER,
        scope="read",
        server=oauth.AuthorizationServer(
            issuer=ISSUER,
            authorization_endpoint=ISSUER + "/authorize",
            token_endpoint=ISSUER + "/token",
            registration_endpoint=ISSUER + "/register",
            iss_parameter=True,
        ),
    )


@pytest.mark.asyncio
async def test_discovery_without_a_hint_tries_the_path_then_the_root(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    issuer = "https://login.example.test/tenant"
    answers: dict[tuple[str, str], Answer] = {
        ("GET", PRM_ROOT): httpx.Response(
            200,
            json=protected_resource(
                resource="https://mcp.example.test/",
                authorization_servers=[issuer],
                scopes_supported=["files:read", "files:write"],
            ),
        ),
        ("GET", issuer + "/.well-known/openid-configuration"): httpx.Response(
            200,
            json=authorization_server(
                issuer=issuer,
                authorization_endpoint=issuer + "/authorize",
                token_endpoint=issuer + "/token",
                registration_endpoint=None,
            ),
        ),
    }
    script = remote(answers)
    plan = await oauth.discover(SERVER, oauth.Challenge())
    assert script.visited == [
        f"GET {PRM}",
        f"GET {PRM_ROOT}",
        "GET https://login.example.test/.well-known/oauth-authorization-server/tenant",
        "GET https://login.example.test/.well-known/openid-configuration/tenant",
        f"GET {issuer}/.well-known/openid-configuration",
    ]
    # The resource the metadata names; the scopes it lists when the challenge named none.
    assert plan.resource == "https://mcp.example.test/"
    assert plan.scope == "files:read files:write"
    assert plan.server.registration_endpoint is None and not plan.server.iss_parameter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource, server",
    [
        # Metadata for another origin, or for a path the server is not under.
        ({"resource": "https://other.example.test/mcp"}, {}),
        ({"resource": "https://mcp.example.test/admin"}, {}),
        ({"authorization_servers": []}, {}),
        ({"authorization_servers": ["http://auth.example.test"]}, {}),
        # A mix-up: the metadata of another issuer than the one named.
        ({}, {"issuer": "https://evil.example.test"}),
        # PKCE with S256 is required; plain or none is refused.
        ({}, {"code_challenge_methods_supported": ["plain"]}),
        ({}, {"code_challenge_methods_supported": None}),
        ({}, {"response_types_supported": ["token"]}),
        ({}, {"token_endpoint": "http://auth.example.test/token"}),
        ({}, {"authorization_endpoint": "https://user:pw@auth.example.test/authorize"}),
        ({}, {"token_endpoint": None}),
    ],
)
async def test_discovery_refuses_metadata_that_cannot_be_trusted(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
    resource: dict[str, Any],
    server: dict[str, Any],
) -> None:
    remote(
        {
            ("GET", PRM): httpx.Response(200, json=protected_resource(**resource)),
            ("GET", AS_METADATA): httpx.Response(200, json=authorization_server(**server)),
        }
    )
    with pytest.raises(LonoraError) as caught:
        await oauth.discover(SERVER, oauth.Challenge(resource_metadata=PRM))
    assert caught.value.code == "mcp_sign_in_unsupported"


@pytest.mark.asyncio
async def test_discovery_without_metadata_is_unsupported(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    script = remote({("GET", PRM): httpx.Response(302, headers={"Location": PRM_ROOT})})
    with pytest.raises(LonoraError) as caught:
        await oauth.discover(SERVER, oauth.Challenge())
    assert caught.value.code == "mcp_sign_in_unsupported"
    # A redirect is never followed: the metadata is where the specification puts it.
    assert script.visited == [f"GET {PRM}", f"GET {PRM_ROOT}"]


@pytest.mark.asyncio
async def test_registration_asks_for_a_public_client_with_lonora_s_callback(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    script = remote(
        {("POST", ISSUER + "/register"): httpx.Response(201, json={"client_id": "lonora-1"})}
    )
    server = oauth.AuthorizationServer(
        issuer=ISSUER,
        authorization_endpoint=ISSUER + "/authorize",
        token_endpoint=ISSUER + "/token",
        registration_endpoint=ISSUER + "/register",
        iss_parameter=False,
    )
    assert await oauth.register(server, CALLBACK, "read") == oauth.Client("lonora-1")
    assert json.loads(script.requests[0].content) == {
        "client_name": "Lonora",
        "redirect_uris": [CALLBACK],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "read",
    }
    remote(
        {
            ("POST", ISSUER + "/register"): httpx.Response(
                200,
                json={
                    "client_id": "lonora-2",
                    "client_secret": "client-secret-value",
                    "token_endpoint_auth_method": "client_secret_basic",
                },
            )
        }
    )
    assert await oauth.register(server, CALLBACK, None) == oauth.Client(
        "lonora-2", "client-secret-value", "client_secret_basic"
    )
    for answer in (
        httpx.Response(201, json={"client_secret": "x"}),
        httpx.Response(201, json={"client_id": "a\nb"}),
        # Saved as a workspace secret: a value shorter than three characters cannot be.
        httpx.Response(
            201,
            json={
                "client_id": "c",
                "client_secret": "xy",
                "token_endpoint_auth_method": "client_secret_post",
            },
        ),
        httpx.Response(400, json={"error": "invalid_redirect_uri"}),
        httpx.Response(201, text="not json"),
    ):
        remote({("POST", ISSUER + "/register"): answer})
        with pytest.raises(LonoraError) as caught:
            await oauth.register(server, CALLBACK, None)
        assert caught.value.code == "mcp_sign_in_failed"
    # Without a registration endpoint Lonora has no client to sign in with.
    with pytest.raises(LonoraError) as caught:
        await oauth.register(
            oauth.AuthorizationServer(ISSUER, ISSUER + "/a", ISSUER + "/t", None, False),
            CALLBACK,
            None,
        )
    assert caught.value.code == "mcp_sign_in_unsupported"


def test_pkce_and_the_authorization_address() -> None:
    verifier, challenge = oauth.pkce_pair()
    assert re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
    digest = hashlib.sha256(verifier.encode()).digest()
    assert challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert oauth.pkce_pair()[0] != verifier
    plan = oauth.SignInPlan(
        resource=SERVER,
        scope="files:read",
        server=oauth.AuthorizationServer(
            ISSUER, ISSUER + "/authorize?tenant=7", ISSUER + "/token", None, False
        ),
    )
    address = oauth.authorization_url(plan, oauth.Client("c-1"), CALLBACK, "state-1", challenge)
    parts = urlsplit(address)
    assert address.startswith(ISSUER + "/authorize?")
    assert parse_qs(parts.query) == {
        # The endpoint's own query is kept.
        "tenant": ["7"],
        "response_type": ["code"],
        "client_id": ["c-1"],
        "redirect_uri": [CALLBACK],
        "state": ["state-1"],
        "code_challenge": [challenge],
        "code_challenge_method": ["S256"],
        "resource": [SERVER],
        "scope": ["files:read"],
    }


def form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode())


@pytest.mark.asyncio
async def test_the_code_exchange_sends_the_verifier_and_checks_the_tokens(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    token = ("POST", ISSUER + "/token")
    script = remote(
        {
            token: httpx.Response(
                200,
                json={
                    "access_token": "access-1",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "refresh_token": "refresh-1",
                },
            )
        }
    )
    tokens = await oauth.exchange_code(
        ISSUER + "/token", SERVER, oauth.Client("c-1"), "code-1", "verifier-1", CALLBACK
    )
    assert tokens == oauth.Tokens("access-1", "refresh-1", 3600)
    [sent] = script.requests
    assert form(sent) == {
        "grant_type": ["authorization_code"],
        "code": ["code-1"],
        "redirect_uri": [CALLBACK],
        "code_verifier": ["verifier-1"],
        "resource": [SERVER],
        "client_id": ["c-1"],
    }
    assert "authorization" not in sent.headers
    # A confidential client authenticates as the registration said.
    script = remote({token: httpx.Response(200, json={"access_token": "access-2"})})
    basic = oauth.Client("c:2", "s/2", "client_secret_basic")
    assert (await oauth.exchange_code(ISSUER + "/token", SERVER, basic, "c", "v", CALLBACK)) == (
        oauth.Tokens("access-2", None, None)
    )
    assert (
        script.requests[0].headers["authorization"]
        == "Basic " + base64.b64encode(b"c%3A2:s%2F2").decode()
    )
    assert "client_secret" not in form(script.requests[0])
    script = remote({token: httpx.Response(200, json={"access_token": "access-3"})})
    posted = oauth.Client("c-3", "secret-3", "client_secret_post")
    await oauth.exchange_code(ISSUER + "/token", SERVER, posted, "c", "v", CALLBACK)
    assert form(script.requests[0])["client_secret"] == ["secret-3"]
    for answer in (
        httpx.Response(200, json={"token_type": "Bearer"}),
        httpx.Response(200, json={"access_token": "a", "token_type": "mac"}),
        httpx.Response(200, json={"access_token": "line\nbreak"}),
        httpx.Response(200, json={"access_token": "abc", "expires_in": "soon"}),
        # Tokens are saved as workspace secrets: shorter than three characters, they
        # cannot be.
        httpx.Response(200, json={"access_token": "ab"}),
        httpx.Response(200, json={"access_token": "abc", "refresh_token": "r"}),
        httpx.Response(500, json={"error": "server_error"}),
        httpx.Response(302, headers={"Location": ISSUER + "/elsewhere"}),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, content=b'{"access_token": "' + b"a" * oauth.MAX_BYTES + b'"}'),
    ):
        remote({token: answer})
        with pytest.raises(LonoraError) as caught:
            await oauth.exchange_code(
                ISSUER + "/token", SERVER, oauth.Client("c"), "c", "v", CALLBACK
            )
        assert caught.value.code == "mcp_sign_in_failed"
        # The authorization server's words never become the error.
        assert "server_error" not in str(caught.value)


@pytest.mark.asyncio
async def test_a_refresh_sends_the_refresh_token_for_the_same_resource(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    script = remote(
        {
            ("POST", ISSUER + "/token"): httpx.Response(
                200, json={"access_token": "access-2", "expires_in": 60}
            )
        }
    )
    tokens = await oauth.refresh(ISSUER + "/token", SERVER, oauth.Client("c-1"), "refresh-1")
    # No new refresh token: the caller keeps the one it has.
    assert tokens == oauth.Tokens("access-2", None, 60)
    assert form(script.requests[0]) == {
        "grant_type": ["refresh_token"],
        "refresh_token": ["refresh-1"],
        "resource": [SERVER],
        "client_id": ["c-1"],
    }


@pytest.mark.asyncio
async def test_a_refused_grant_is_told_apart_from_a_server_that_failed(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
) -> None:
    """The token endpoint's refusal (400 or 401, RFC 6749 5.2) means the grant is gone; a
    server that fails or is busy leaves the sign-in as it was, to try again."""
    token = ("POST", ISSUER + "/token")
    for status, code in (
        (400, "mcp_sign_in_refused"),
        (401, "mcp_sign_in_refused"),
        (429, "mcp_sign_in_failed"),
        (500, "mcp_sign_in_failed"),
        (503, "mcp_sign_in_failed"),
    ):
        remote({token: httpx.Response(status, json={"error": "invalid_grant"})})
        with pytest.raises(LonoraError) as caught:
            await oauth.refresh(ISSUER + "/token", SERVER, oauth.Client("c-1"), "refresh-1")
        assert caught.value.code == code, status
        assert "invalid_grant" not in str(caught.value)
    # A lifetime no clock can hold is none: the token is renewed when the server refuses it.
    remote({token: httpx.Response(200, json={"access_token": "access-1", "expires_in": 10**12})})
    tokens = await oauth.refresh(ISSUER + "/token", SERVER, oauth.Client("c-1"), "refresh-1")
    assert tokens == oauth.Tokens("access-1", None, None)


class Drip(httpx.AsyncByteStream):
    """A body that arrives one byte at a time, each within any read timeout."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(40):
            await asyncio.sleep(0.05)
            yield b" "


@pytest.mark.asyncio
async def test_an_answer_is_read_as_sent_and_within_one_deadline(
    remote: Callable[[dict[tuple[str, str], Answer]], Remote],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No decompressor runs before the size limit: Lonora asks for the body as it is and
    refuses an encoded one. One deadline covers the whole answer, however slowly it comes,
    so a renewal never holds its lock for longer."""
    token = ("POST", ISSUER + "/token")
    packed = gzip.compress(json.dumps({"access_token": "a" * 10_000}).encode())
    script = remote(
        {token: httpx.Response(200, content=packed, headers={"Content-Encoding": "gzip"})}
    )
    with pytest.raises(LonoraError) as caught:
        await oauth.exchange_code(ISSUER + "/token", SERVER, oauth.Client("c"), "c", "v", CALLBACK)
    assert caught.value.code == "mcp_sign_in_failed"
    assert script.requests[0].headers["accept-encoding"] == "identity"

    monkeypatch.setattr(oauth, "TIMEOUT_SECONDS", 0.3)
    remote({token: httpx.Response(200, stream=Drip())})
    started = asyncio.get_running_loop().time()
    with pytest.raises(LonoraError) as caught:
        await oauth.refresh(ISSUER + "/token", SERVER, oauth.Client("c"), "refresh-1")
    assert caught.value.code == "mcp_sign_in_failed"
    assert asyncio.get_running_loop().time() - started < 1.5


@pytest.mark.asyncio
async def test_an_address_with_a_port_no_address_can_have_is_refused() -> None:
    """Metadata may name any https address: one whose port is out of range is refused as
    an unsafe address, never raised as another error."""
    with pytest.raises(LonoraError) as caught:
        await oauth.exchange_code(
            "https://auth.example.test:99999/token", SERVER, oauth.Client("c"), "c", "v", CALLBACK
        )
    assert caught.value.code == "mcp_sign_in_failed"


@pytest.mark.asyncio
async def test_a_private_address_is_refused_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"access_token": "a"})

    async def private(url: str) -> str:
        raise LonoraError("private_remote_address_forbidden", 403)

    monkeypatch.setattr(oauth, "validate_public_url", private)
    monkeypatch.setattr(
        oauth, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(answer))
    )
    with pytest.raises(LonoraError) as caught:
        await oauth.exchange_code(ISSUER + "/token", SERVER, oauth.Client("c"), "c", "v", CALLBACK)
    assert caught.value.code == "mcp_sign_in_failed"
    with pytest.raises(LonoraError) as caught:
        await oauth.discover(SERVER, oauth.Challenge(resource_metadata=PRM))
    assert caught.value.code == "mcp_sign_in_unsupported"
    # The probe of the owner's own address says only "no sign-in": saving decides the rest.
    assert await oauth.needs_sign_in(SERVER) is None
    assert requests == []


def test_the_callback_names_the_issuer_it_was_sent_by() -> None:
    assert oauth.issuer_matches(ISSUER, True, ISSUER)
    # A mix-up: another issuer's response, or none where the server promised to name it.
    assert not oauth.issuer_matches(ISSUER, True, "https://evil.example.test")
    assert not oauth.issuer_matches(ISSUER, True, None)
    assert oauth.issuer_matches(ISSUER, False, None)
    assert not oauth.issuer_matches(ISSUER, False, "https://evil.example.test")
