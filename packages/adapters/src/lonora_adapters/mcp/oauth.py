"""Signing in to a remote MCP server: OAuth 2.1 with PKCE, as the MCP authorization
specification asks (protocol 2025-06-18; VISION.md 13.1).

A server that answers Lonora's ``initialize`` without credentials with 401 asks for a
sign-in. Lonora reads the server's protected-resource metadata (RFC 9728), then its
authorization server's metadata (RFC 8414, or OpenID discovery), registers itself as a
public client (RFC 7591), and sends the owner's browser to sign in with a PKCE challenge
(RFC 7636, S256 only) for this server alone (``resource``, RFC 8707). The code that comes
back is exchanged for tokens, which the caller keeps as workspace secrets; a refresh
token renews the access token.

Every request goes to a public https address that passes ``validate_public_url``, follows
no redirect, reads at most ``MAX_BYTES`` as sent (never decompressed) and ends within
``TIMEOUT_SECONDS``. Metadata that cannot be trusted (another origin's resource, another
issuer, no S256) refuses the sign-in (``mcp_sign_in_unsupported``); a server that
misbehaves while signing in fails it (``mcp_sign_in_failed``); a token endpoint that
refuses the grant ends it (``mcp_sign_in_refused``). No remote text and no token is ever
part of an error.
"""

import asyncio
import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url
from lonora_security.secrets import SHORTEST_SECRET

MAX_BYTES = 64 * 1024
TIMEOUT_SECONDS = 15
PROTOCOL_VERSION = "2025-06-18"
UNSUPPORTED = "mcp_sign_in_unsupported"
FAILED = "mcp_sign_in_failed"
REFUSED = "mcp_sign_in_refused"
# A longer lifetime is none at all: the token is renewed when the server refuses it.
MAX_LIFETIME_SECONDS = 10 * 365 * 24 * 3600
RESOURCE_METADATA = "/.well-known/oauth-protected-resource"
CLIENT_METHODS = ("none", "client_secret_basic", "client_secret_post")
ClientMethod = Literal["none", "client_secret_basic", "client_secret_post"]
# A value sent in a header or a form: visible ASCII, as a bearer token is.
VISIBLE = re.compile(r"[\x21-\x7e]{1,8192}")
TOKEN = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
# One item of a WWW-Authenticate header: an auth-param, or the scheme of a challenge.
ITEM = re.compile(
    rf"""\s*,?\s*(?:
        (?P<key>{TOKEN})\s*=\s*(?:"(?P<quoted>(?:[^"\\]|\\.)*)"|(?P<plain>[^\s,"]*))
      | (?P<scheme>{TOKEN})(?:\s+[A-Za-z0-9._~+/-]+=*(?=\s*(?:,|$)))?
    )""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class Challenge:
    """What a server's 401 names for the sign-in, when it names anything."""

    resource_metadata: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class AuthorizationServer:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None
    # It names itself in the callback (RFC 9207), so a callback that does not is refused.
    iss_parameter: bool


@dataclass(frozen=True)
class SignInPlan:
    """Where to sign in, for which resource, with which scope."""

    resource: str
    scope: str | None
    server: AuthorizationServer


@dataclass(frozen=True)
class Client:
    """Lonora as the authorization server registered it."""

    client_id: str
    client_secret: str | None = None
    method: ClientMethod = "none"


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None


def refusal(code: str) -> LonoraError:
    return LonoraError(code, 422 if code == UNSUPPORTED else 502)


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False)


async def fetch(
    method: str,
    url: str,
    *,
    unsafe: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    """One request to a public https address: its status and at most ``MAX_BYTES`` of
    its body as sent, all within ``TIMEOUT_SECONDS`` however slowly it arrives. No
    decompressor runs before the limit: an encoded body is refused. ``unsafe`` is the
    refusal for an address that is not one."""
    try:
        await validate_public_url(url)
    except (LonoraError, ValueError):
        raise refusal(unsafe) from None
    sent = {**(headers or {}), "Accept-Encoding": "identity"}
    try:
        async with (
            asyncio.timeout(TIMEOUT_SECONDS),
            http_client() as client,
            client.stream(method, url, headers=sent, json=body, data=form) as response,
        ):
            encoding = response.headers.get("Content-Encoding", "identity").strip().casefold()
            if encoding not in {"", "identity"}:
                raise refusal(FAILED)
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise refusal(FAILED)
            return response.status_code, bytes(raw)
    except (TimeoutError, httpx.HTTPError):
        raise refusal(FAILED) from None


def json_object(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise refusal(code) from None
    if not isinstance(value, dict):
        raise refusal(code)
    return cast(dict[str, Any], value)


def https_url(value: Any) -> str:
    """An https address with a host and no user name, password or fragment."""
    if not isinstance(value, str) or len(value) > 2048:
        raise refusal(UNSUPPORTED)
    try:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.fragment:
            raise ValueError
    except ValueError:
        raise refusal(UNSUPPORTED) from None
    return value


def challenges(header: str) -> list[tuple[str, dict[str, str]]]:
    """The challenges of a WWW-Authenticate header, each scheme with its parameters."""
    found: list[tuple[str, dict[str, str]]] = []
    position = 0
    while position < len(header):
        match = ITEM.match(header, position)
        if match is None or match.end() == position:
            break
        position = match.end()
        if match["scheme"]:
            found.append((match["scheme"].lower(), {}))
        elif found:
            quoted = match["quoted"]
            value = re.sub(r"\\(.)", r"\1", quoted) if quoted is not None else match["plain"]
            found[-1][1].setdefault(match["key"].lower(), value)
    return found


def bearer_challenge(header: str | None) -> Challenge | None:
    """The Bearer challenge of a 401: an empty one when the header is missing (a 401
    alone asks for a sign-in), None when only another scheme is asked for."""
    if header is None or not header.strip():
        return Challenge()
    for scheme, params in challenges(header):
        if scheme == "bearer":
            return Challenge(
                resource_metadata=params.get("resource_metadata") or None,
                scope=params.get("scope") or None,
            )
    return None


async def needs_sign_in(url: str) -> Challenge | None:
    """Whether the server at ``url`` asks for a sign-in: its answer to ``initialize``
    without credentials is 401 with a Bearer challenge, or with none. Anything else (it
    answered, refused otherwise, or could not be reached) is no sign-in. Only the status
    and the headers are read, never a stream the server keeps open."""
    try:
        await validate_public_url(url)
        async with (
            asyncio.timeout(TIMEOUT_SECONDS),
            http_client() as client,
            client.stream(
                "POST",
                url,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Accept-Encoding": "identity",
                    "MCP-Protocol-Version": PROTOCOL_VERSION,
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "Lonora", "version": "0.2.0"},
                    },
                },
            ) as response,
        ):
            if response.status_code != 401:
                return None
            return bearer_challenge(response.headers.get("WWW-Authenticate"))
    except (LonoraError, ValueError, TimeoutError, httpx.HTTPError):
        return None


def resource_candidates(url: str, hint: str | None) -> list[str]:
    """Where the server's protected-resource metadata may be (RFC 9728): the address
    its challenge named, then the well-known address with its path, then without."""
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    found = [hint] if hint else []
    if parts.path and parts.path != "/":
        found.append(origin + RESOURCE_METADATA + parts.path)
    return [*found, origin + RESOURCE_METADATA]


def server_candidates(issuer: str) -> list[str]:
    """Where an authorization server's metadata may be (RFC 8414, OpenID discovery)."""
    parts = urlsplit(issuer)
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")
    if not path:
        return [
            origin + "/.well-known/oauth-authorization-server",
            origin + "/.well-known/openid-configuration",
        ]
    return [
        origin + "/.well-known/oauth-authorization-server" + path,
        origin + "/.well-known/openid-configuration" + path,
        origin + path + "/.well-known/openid-configuration",
    ]


async def first_metadata(candidates: list[str]) -> dict[str, Any]:
    """The first candidate that answers 200 with a JSON object; none is unsupported."""
    for candidate in candidates:
        status, raw = await fetch(
            "GET",
            https_url(candidate),
            unsafe=UNSUPPORTED,
            headers={"Accept": "application/json", "MCP-Protocol-Version": PROTOCOL_VERSION},
        )
        if status == 200:
            return json_object(raw, UNSUPPORTED)
    raise refusal(UNSUPPORTED)


def covers(resource: str, url: str) -> bool:
    """The metadata's resource is the server's own: the same origin, and a path the
    server's path is under."""
    named, server = urlsplit(resource), urlsplit(url)
    if (named.scheme, named.netloc.lower()) != (server.scheme, server.netloc.lower()):
        return False
    prefix = named.path if named.path.endswith("/") else named.path + "/"
    path = server.path if server.path.endswith("/") else server.path + "/"
    return path.startswith(prefix)


async def authorization_server(issuer: str) -> AuthorizationServer:
    metadata = await first_metadata(server_candidates(issuer))
    named = metadata.get("issuer")
    # A mix-up: the metadata must be the issuer's own (RFC 8414 3.3).
    if not isinstance(named, str) or named.rstrip("/") != issuer.rstrip("/"):
        raise refusal(UNSUPPORTED)
    methods = metadata.get("code_challenge_methods_supported")
    if not isinstance(methods, list) or "S256" not in methods:
        raise refusal(UNSUPPORTED)
    responses = metadata.get("response_types_supported")
    if responses is not None and (not isinstance(responses, list) or "code" not in responses):
        raise refusal(UNSUPPORTED)
    registration = metadata.get("registration_endpoint")
    return AuthorizationServer(
        issuer=named,
        authorization_endpoint=https_url(metadata.get("authorization_endpoint")),
        token_endpoint=https_url(metadata.get("token_endpoint")),
        registration_endpoint=None if registration is None else https_url(registration),
        iss_parameter=metadata.get("authorization_response_iss_parameter_supported") is True,
    )


async def discover(url: str, challenge: Challenge) -> SignInPlan:
    """Where to sign in to the server at ``url``, from its metadata and its server's."""
    metadata = await first_metadata(resource_candidates(url, challenge.resource_metadata))
    resource = metadata.get("resource")
    if not isinstance(resource, str) or not covers(https_url(resource), url):
        raise refusal(UNSUPPORTED)
    servers = metadata.get("authorization_servers")
    if not isinstance(servers, list) or not servers:
        raise refusal(UNSUPPORTED)
    server = await authorization_server(https_url(cast(list[Any], servers)[0]))
    scope = challenge.scope
    supported = metadata.get("scopes_supported")
    if scope is None and isinstance(supported, list) and supported:
        scope = " ".join(str(item) for item in cast(list[Any], supported))
    return SignInPlan(resource=resource, scope=scope, server=server)


def visible(value: Any) -> bool:
    return isinstance(value, str) and VISIBLE.fullmatch(value) is not None


def storable(value: Any) -> bool:
    """A token or client secret Lonora can keep as a workspace secret, which the scan of
    workspace output must be able to find."""
    return visible(value) and len(value) >= SHORTEST_SECRET


async def register(server: AuthorizationServer, redirect_uri: str, scope: str | None) -> Client:
    """Lonora registered as a client of this server (RFC 7591), public unless the
    server says otherwise."""
    if server.registration_endpoint is None:
        raise refusal(UNSUPPORTED)
    body: dict[str, Any] = {
        "client_name": "Lonora",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scope:
        body["scope"] = scope
    status, raw = await fetch(
        "POST",
        server.registration_endpoint,
        unsafe=FAILED,
        headers={"Accept": "application/json"},
        body=body,
    )
    if status not in (200, 201):
        raise refusal(FAILED)
    data = json_object(raw, FAILED)
    client_id, secret = data.get("client_id"), data.get("client_secret")
    method = data.get("token_endpoint_auth_method") or ("client_secret_basic" if secret else "none")
    if not visible(client_id) or method not in CLIENT_METHODS:
        raise refusal(FAILED)
    if method == "none":
        return Client(cast(str, client_id))
    if not storable(secret):
        raise refusal(FAILED)
    return Client(cast(str, client_id), cast(str, secret), cast(ClientMethod, method))


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()


def authorization_url(
    plan: SignInPlan, client: Client, redirect_uri: str, state: str, challenge: str
) -> str:
    """The page the owner's browser opens to sign in: the endpoint's own query, then
    the request, for this resource alone."""
    request = {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": plan.resource,
    }
    if plan.scope:
        request["scope"] = plan.scope
    parts = urlsplit(plan.server.authorization_endpoint)
    kept = [
        item for item in parse_qsl(parts.query, keep_blank_values=True) if item[0] not in request
    ]
    return urlunsplit(parts._replace(query=urlencode([*kept, *request.items()])))


async def token_request(
    token_endpoint: str, resource: str, client: Client, fields: dict[str, str]
) -> Tokens:
    form = {**fields, "resource": resource}
    headers = {"Accept": "application/json"}
    if client.method == "client_secret_basic":
        credentials = quote(client.client_id, safe="") + ":"
        credentials += quote(client.client_secret or "", safe="")
        headers["Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode()
    else:
        form["client_id"] = client.client_id
        if client.method == "client_secret_post":
            form["client_secret"] = client.client_secret or ""
    status, raw = await fetch("POST", token_endpoint, unsafe=FAILED, headers=headers, form=form)
    if status in (400, 401):
        # The grant or the client is refused (RFC 6749 5.2): asking again cannot help.
        raise refusal(REFUSED)
    if status != 200:
        raise refusal(FAILED)
    data = json_object(raw, FAILED)
    access, refresh_token = data.get("access_token"), data.get("refresh_token")
    token_type, expires_in = data.get("token_type", "Bearer"), data.get("expires_in")
    if not storable(access) or not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise refusal(FAILED)
    if refresh_token is not None and not storable(refresh_token):
        raise refusal(FAILED)
    if expires_in is not None and (
        isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0
    ):
        raise refusal(FAILED)
    if expires_in is not None and expires_in > MAX_LIFETIME_SECONDS:
        expires_in = None
    return Tokens(cast(str, access), cast(str | None, refresh_token), expires_in)


async def exchange_code(
    token_endpoint: str, resource: str, client: Client, code: str, verifier: str, redirect: str
) -> Tokens:
    """The tokens for the code the owner's sign-in returned, proven with the verifier."""
    return await token_request(
        token_endpoint,
        resource,
        client,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
            "code_verifier": verifier,
        },
    )


async def refresh(token_endpoint: str, resource: str, client: Client, refresh_token: str) -> Tokens:
    """A new access token for the same resource. No new refresh token in the answer
    means the caller keeps the one it has."""
    return await token_request(
        token_endpoint,
        resource,
        client,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
    )


def issuer_matches(issuer: str, names_itself: bool, iss: str | None) -> bool:
    """The callback came from the server the sign-in was sent to (RFC 9207): it names
    that issuer, or names none when the server never said it would."""
    if iss is None:
        return not names_itself
    return iss == issuer
