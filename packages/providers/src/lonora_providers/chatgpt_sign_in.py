"""Sign in with ChatGPT: the owner's ChatGPT plan for OpenAI's public Responses API (VISION
Amendment 4; docs/proposals/model-catalog-and-chatgpt-signin.md, section 4).

OpenAI's official flow for open-source apps ("ChatGPT plan usage in your open-source app"),
as OpenMausBot runs it: dynamic client registration (``dynamic_agent_client`` the first
time, the issued ``oaiapp_…`` id after), a stable host id, a fresh ``state``, ``nonce`` and
PKCE verifier for each attempt, the code exchanged with no client secret, the ID token
verified against OpenAI's published keys, and plan use only with the granted
``chatgpt.tokens.use.direct`` scope. Never the Codex CLI's client id or ChatGPT's private
endpoints (VISION 12.2).

Lonora runs on a server, so OpenAI's loopback callback does not reach it: the owner pastes
the address the browser lands on, and Lonora checks it is that callback, each parameter
once, with this attempt's ``state``.

Storage (4.3): the credential and the pending attempt are encrypted values of scope
``provider`` (``openai_chatgpt``, ``openai_chatgpt_pending``), out of the workspace; the
host id and the account's models are settings. Refreshes rotate the refresh token, so they
run under one advisory lock per owner, which re-reads the stored copy and replaces the
token set in the same transaction. Provider text is never kept, shown or logged.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

import httpx
import jwt
from dotenv import dotenv_values
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_core.user_error import LonoraError
from lonora_db.model_credentials import CONNECTION_SETTING
from lonora_db.schema import SecretRow, SettingRow
from lonora_db.transactions import SettingsRepository
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import PLAN_MODELS

log = logging.getLogger("lonora.chatgpt_sign_in")

PROVIDER = "openai_chatgpt"
PENDING = "openai_chatgpt_pending"
# OpenAI's sign-in, on its official paths only (tests/test_model_access_guard.py).
ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
JWKS_URL = "https://auth.openai.com/.well-known/jwks.json"
DISCOVERY_URL = "https://auth.openai.com/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
MODELS_URL = RESOURCE + "/models"
# The loopback callback OpenAI sends the browser to: never ``localhost``.
REDIRECT_URI = "http://127.0.0.1:1455/auth/callback"
DYNAMIC_CLIENT = "dynamic_agent_client"
AGENT_NAME = "Lonora"
DIRECT_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + DIRECT_SCOPE
HOST_SETTING = "chatgpt_host_id"
FLAG = "LONORA_CHATGPT_SIGN_IN"
PENDING_SECONDS = 15 * 60
# The access token is renewed before its last minute.
REFRESH_MARGIN = 60
# The account's models are read again at most this often while the plan is used.
MODELS_SECONDS = 15 * 60
CLOCK_LEEWAY = 30
RESPONSE_LIMIT = 1_048_576
TERMINAL_REFRESH = frozenset(
    {
        "invalid_grant",
        "invalid_refresh_token",
        "token_expired",
        "refresh_token_expired",
        "refresh_token_invalidated",
        "refresh_token_reused",
    }
)


def sign_in_enabled() -> bool:
    """``LONORA_CHATGPT_SIGN_IN`` (default on). Lonora Cloud sets it off until OpenAI
    approves it for remotely hosted apps (M8); off, nothing offers or uses the sign-in."""
    value = os.environ.get(FLAG) or dotenv_values(".env").get(FLAG) or "on"
    return value.strip().lower() not in {"off", "0", "false", "no"}


def require_enabled() -> None:
    if not sign_in_enabled():
        raise LonoraError("chatgpt_sign_in_unavailable", 409)


def http_client() -> httpx.AsyncClient:
    """OpenAI's sign-in and model endpoints, never following a redirect."""
    return httpx.AsyncClient(timeout=httpx.Timeout(15), follow_redirects=False)


class Unreachable(Exception):
    """OpenAI did not answer, or answered with more than an answer can be."""


@dataclass(frozen=True)
class Credential:
    """One registration: the issued client id and host, the verified account, and its
    tokens (none after sign-out or a refused refresh; ``sign_in_again`` says which)."""

    client_id: str
    host_id: str
    subject: str | None = None
    email: str | None = None
    id_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    scopes: tuple[str, ...] = ()
    expires_at: float = 0.0
    earliest_refresh_at: float | None = None
    sign_in_again: bool = False

    @property
    def plan(self) -> bool:
        """Signed in with plan use allowed: requests may use the ChatGPT plan."""
        return bool(self.access_token) and DIRECT_SCOPE in self.scopes

    def cleared(self, *, sign_in_again: bool) -> "Credential":
        """Without tokens; the client id, host and account mapping stay for a later sign-in."""
        return replace(
            self,
            id_token=None,
            access_token=None,
            refresh_token=None,
            scopes=(),
            expires_at=0.0,
            earliest_refresh_at=None,
            sign_in_again=sign_in_again,
        )


def credential_of(value: str | None) -> Credential | None:
    if value is None:
        return None
    record = json.loads(value)
    record["scopes"] = tuple(record.get("scopes") or ())
    return Credential(**record)


def credential_json(credential: Credential) -> str:
    record = asdict(credential)
    record["scopes"] = list(credential.scopes)
    return json.dumps(record)


async def _lock(session: AsyncSession, owner_id: str) -> None:
    # One lock per owner's credential: refreshes, a finished sign-in and sign-out never
    # interleave, so a rotated refresh token is never used twice.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "chatgpt-sign-in:" + owner_id},
    )


def _callback(address: str) -> dict[str, str]:
    """The pasted callback's parameters: the exact callback address, each parameter
    once, nothing else."""
    try:
        parts = urlsplit(address.strip())
        port = parts.port
    except ValueError:
        raise LonoraError("chatgpt_address_invalid", 422) from None
    if (
        len(address) > 16384
        or parts.scheme != "http"
        or parts.hostname != "127.0.0.1"
        or port != 1455
        or parts.path != "/auth/callback"
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise LonoraError("chatgpt_address_invalid", 422)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    params = dict(pairs)
    if len(params) != len(pairs) or "state" not in params:
        raise LonoraError("chatgpt_address_invalid", 422)
    return params


def _string(value: Any, limit: int = 65536) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


class ChatGptSignIn:
    """The owner's ChatGPT registration on this installation."""

    def __init__(self, store: EncryptedSecretStore):
        self.store, self.db = store, store.db

    # Storage ------------------------------------------------------------------------

    async def _value(self, session: AsyncSession, name: str) -> str | None:
        row = await session.scalar(
            select(SecretRow)
            .where(
                SecretRow.owner_id == self.store.owner_id,
                SecretRow.scope == "provider",
                SecretRow.name == name,
            )
            .execution_options(populate_existing=True)
        )
        return self.store.cipher.decrypt(row.ciphertext) if row else None

    async def _saved(self, session: AsyncSession) -> Credential | None:
        return credential_of(await self._value(session, PROVIDER))

    async def _save(self, session: AsyncSession, credential: Credential) -> str:
        return await self.store.write_in_session(
            session, PROVIDER, credential_json(credential), "provider"
        )

    async def _forget(self, session: AsyncSession, name: str) -> None:
        row = await session.scalar(
            select(SecretRow).where(
                SecretRow.owner_id == self.store.owner_id,
                SecretRow.scope == "provider",
                SecretRow.name == name,
            )
        )
        if row is not None:
            await session.delete(row)

    async def credential(self) -> Credential | None:
        async with self.db.sessions() as session:
            return await self._saved(session)

    async def usable(self) -> bool:
        """Signed in with plan use, read without asking OpenAI."""
        if not sign_in_enabled():
            return False
        saved = await self.credential()
        return saved is not None and saved.plan

    async def status(self) -> dict[str, Any]:
        """What the settings list shows: the account, plan use, and whether to sign in again."""
        saved = await self.credential()
        return {
            "email": saved.email if saved and saved.subject else None,
            "plan": bool(saved and saved.plan),
            "sign_in_again": bool(saved and saved.sign_in_again),
        }

    # OpenAI ---------------------------------------------------------------------------

    async def _call(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        token: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            async with (
                http_client() as client,
                client.stream(method, url, data=data, headers=headers) as response,
            ):
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > RESPONSE_LIMIT:
                        raise Unreachable()
                status = response.status_code
        except httpx.HTTPError:
            raise Unreachable() from None
        try:
            value: Any = json.loads(body) if body else {}
        except ValueError:
            value = {}
        return status, cast(dict[str, Any], value) if isinstance(value, dict) else {}

    async def _keys(self) -> jwt.PyJWKSet:
        """OpenAI's published ID-token keys; fetched before any token is exchanged, so
        nothing fallible stands between receiving a rotated token and saving it."""
        status, body = await self._call("GET", JWKS_URL)
        if status != 200:
            raise Unreachable()
        try:
            return jwt.PyJWKSet.from_dict(body)
        except jwt.PyJWTError:
            raise LonoraError("chatgpt_identity_invalid", 502) from None

    def _identity(
        self, id_token: str, client_id: str, keys: jwt.PyJWKSet, nonce: str | None
    ) -> tuple[str, str | None]:
        """The verified ``sub`` and email of an ID token: OpenAI's signature (RS256 or
        ES256), issuer, audience the issued client id, ``exp``, ``iat`` and the nonce."""
        try:
            header = jwt.get_unverified_header(id_token)
            algorithm = header.get("alg")
            if algorithm not in {"RS256", "ES256"}:
                raise jwt.InvalidAlgorithmError()
            kid = header.get("kid")
            candidates = [key for key in keys.keys if kid is None or key.key_id == kid]
            if len(candidates) != 1:
                raise jwt.InvalidKeyError()
            claims = jwt.decode(
                id_token,
                candidates[0].key,
                algorithms=[algorithm],
                audience=client_id,
                issuer=ISSUER,
                leeway=CLOCK_LEEWAY,
                options={"require": ["sub", "exp", "iat", "iss", "aud"]},
            )
        except jwt.PyJWTError:
            raise LonoraError("chatgpt_identity_invalid", 502) from None
        audience = claims.get("aud")
        subject = _string(claims.get("sub"), 512)
        if (
            subject is None
            or not isinstance(claims.get("iat"), (int, float))
            or claims["iat"] > time.time() + CLOCK_LEEWAY
            or (
                isinstance(audience, list)
                and len(cast(list[Any], audience)) > 1
                and claims.get("azp") != client_id
            )
            or (nonce is not None and not hmac.compare_digest(str(claims.get("nonce", "")), nonce))
        ):
            raise LonoraError("chatgpt_identity_invalid", 502)
        return subject, _string(claims.get("email"), 320)

    @staticmethod
    def _tokens(body: dict[str, Any], previous: Credential | None = None) -> dict[str, Any]:
        """A token response's set; a refresh keeps the scopes and ID token it does not repeat."""
        access = _string(body.get("access_token"))
        expires_in = body.get("expires_in")
        kind = body.get("token_type")
        scope = body.get("scope")
        if (
            access is None
            or not isinstance(kind, str)
            or kind.lower() != "bearer"
            or not isinstance(expires_in, (int, float))
            or not 0 < expires_in <= 86400
            or (scope is not None and not isinstance(scope, str))
        ):
            raise ValueError()
        id_token = _string(body.get("id_token")) or (previous.id_token if previous else None)
        if isinstance(scope, str):
            scopes = tuple(scope.split())
        else:
            scopes = previous.scopes if previous else ()
        refresh = _string(body.get("refresh_token"))
        if id_token is None or not scopes or (DIRECT_SCOPE in scopes and refresh is None):
            raise ValueError()
        earliest = body.get("earliest_refresh_at")
        return {
            "access_token": access,
            "refresh_token": refresh,
            "id_token": id_token,
            "scopes": scopes,
            "expires_at": time.time() + float(expires_in),
            "earliest_refresh_at": float(earliest) if isinstance(earliest, (int, float)) else None,
        }

    async def _offered(self, access_token: str) -> list[str] | None:
        """The slugs the account's model list shows (``visibility: list``); None when it
        could not be read."""
        try:
            status, body = await self._call("GET", MODELS_URL, token=access_token)
        except Unreachable:
            return None
        models = body.get("models")
        if status != 200 or not isinstance(models, list):
            log.warning("chatgpt_models_unread status=%s", status)
            return None
        return [
            slug
            for item in cast(list[Any], models)
            if isinstance(item, dict)
            and cast(dict[str, Any], item).get("visibility") == "list"
            and (slug := _string(cast(dict[str, Any], item).get("slug"), 256))
        ]

    # The sign-in ----------------------------------------------------------------------

    async def _host_id(self, session: AsyncSession) -> str:
        """This installation's ``ext_agent_host_id``: created once, an identifier only."""
        settings = SettingsRepository()
        saved = (await settings.get(session, HOST_SETTING)).get("host_id")
        if isinstance(saved, str):
            return saved
        host = "urn:uuid:" + str(uuid.uuid4())
        await settings.put(session, HOST_SETTING, {"host_id": host})
        return host

    async def start(self, card_id: str) -> dict[str, Any]:
        """The authorization address for one attempt, its state kept encrypted for 15
        minutes. A registered account signs in with its issued id and its hints; plan use
        declined before asks for consent again."""
        require_enabled()
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        expires = time.time() + PENDING_SECONDS
        async with self.db.sessions() as session, session.begin():
            await _lock(session, self.store.owner_id)
            host = await self._host_id(session)
            saved = await self._saved(session)
            client = saved.client_id if saved else None
            params = {"client_id": client or DYNAMIC_CLIENT}
            if client is None:
                params["agent_name_hint"] = AGENT_NAME
            params["ext_agent_host_id"] = host
            if saved and saved.id_token:
                params["id_token_hint"] = saved.id_token
            if saved and saved.email:
                params["login_hint"] = saved.email
            if saved and saved.access_token and DIRECT_SCOPE not in saved.scopes:
                params["prompt"] = "consent"
            challenge = hashlib.sha256(verifier.encode()).digest()
            params.update(
                response_type="code",
                redirect_uri=REDIRECT_URI,
                scope=SCOPES,
                resource=RESOURCE,
                state=state,
                nonce=nonce,
                code_challenge_method="S256",
                code_challenge=base64.urlsafe_b64encode(challenge).decode().rstrip("="),
            )
            pending = {
                "card_id": card_id,
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "client_id": client,
                "subject": saved.subject if saved else None,
                "host_id": host,
                "expires_at": expires,
            }
            await self.store.write_in_session(session, PENDING, json.dumps(pending), "provider")
        # The address may carry the ID token as a hint: it goes to the owner's browser only,
        # and is never logged.
        return {
            "authorization_url": AUTHORIZE_URL + "?" + urlencode(params, quote_via=quote),
            "expires_at": datetime.fromtimestamp(expires, UTC).isoformat(),
        }

    async def _take_pending(self, card_id: str, state: str) -> dict[str, Any]:
        """The attempt the pasted address answers, removed as it is taken: one address,
        one exchange. An address of another attempt leaves this one waiting."""
        async with self.db.sessions() as session, session.begin():
            await _lock(session, self.store.owner_id)
            value = await self._value(session, PENDING)
            pending: dict[str, Any] | None = json.loads(value) if value else None
            if (
                pending is None
                or pending["card_id"] != card_id
                or pending["expires_at"] <= time.time()
            ):
                raise LonoraError("chatgpt_sign_in_expired", 409)
            if not hmac.compare_digest(state.encode(), str(pending["state"]).encode()):
                raise LonoraError("chatgpt_state_mismatch", 422)
            await self._forget(session, PENDING)
            return pending

    async def finish(self, card_id: str, address: str) -> dict[str, Any]:
        """Check the pasted address, exchange its code, verify the identity and save the
        credential. Returns the account and the number of listed models it offers; plan
        use declined saves the sign-in and raises ``chatgpt_plan_use_declined``."""
        require_enabled()
        params = _callback(address)
        pending = await self._take_pending(card_id, params["state"])
        if "error" in params:
            # OAuth's own answer: the owner did not approve, or the attempt failed.
            if params["error"] == "access_denied":
                raise LonoraError("chatgpt_sign_in_declined", 409)
            raise LonoraError("chatgpt_sign_in_failed", 502)
        client = params.get("client_id") or pending["client_id"]
        if (
            not _string(client, 256)
            or client == DYNAMIC_CLIENT
            or (pending["client_id"] and client != pending["client_id"])
        ):
            # A registration without its issued id is incomplete, and a returning sign-in
            # never takes another registration's id.
            raise LonoraError("chatgpt_client_mismatch", 409)
        code = _string(params.get("code"), 4096)
        if code is None:
            raise LonoraError("chatgpt_sign_in_failed", 502)
        try:
            keys = await self._keys()
            status, body = await self._call(
                "POST",
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": client,
                    "code": code,
                    "code_verifier": pending["verifier"],
                    "redirect_uri": REDIRECT_URI,
                    "resource": RESOURCE,
                },
            )
        except Unreachable:
            raise LonoraError("chatgpt_unreachable", 503) from None
        if status != 200:
            if body.get("error") == "invalid_grant":
                # A used or expired code: the next attempt keeps this issued id, so no
                # second client is registered.
                await self._keep_client(client, pending["host_id"])
                raise LonoraError("chatgpt_sign_in_code_expired", 409)
            log.warning("chatgpt_exchange_refused status=%s", status)
            raise LonoraError("chatgpt_sign_in_failed", 502)
        try:
            tokens = self._tokens(body)
        except ValueError:
            raise LonoraError("chatgpt_sign_in_failed", 502) from None
        subject, email = self._identity(tokens["id_token"], client, keys, pending["nonce"])
        if pending["subject"] and subject != pending["subject"]:
            raise LonoraError("chatgpt_other_account", 409)
        plan = DIRECT_SCOPE in tokens["scopes"]
        offered = await self._offered(tokens["access_token"]) if plan else None
        async with self.db.sessions() as session, session.begin():
            await _lock(session, self.store.owner_id)
            current = await self._saved(session)
            if current is not None and current.subject is not None:
                if current.subject != subject:
                    raise LonoraError("chatgpt_other_account", 409)
                if current.client_id != client:
                    raise LonoraError("chatgpt_client_mismatch", 409)
            await self._save(
                session,
                Credential(
                    client_id=client,
                    host_id=pending["host_id"],
                    subject=subject,
                    email=email,
                    **tokens,
                ),
            )
            # A new sign-in starts the account's models afresh, refusals included.
            await SettingsRepository().put(
                session,
                PLAN_MODELS,
                {
                    "subject": subject,
                    "offered": offered,
                    "read_at": time.time() if offered is not None else None,
                    "refused": [],
                },
            )
        if not plan:
            raise LonoraError("chatgpt_plan_use_declined", 409)
        return {"email": email, "offered": offered}

    async def _keep_client(self, client: str, host: str) -> None:
        async with self.db.sessions() as session, session.begin():
            await _lock(session, self.store.owner_id)
            if await self._saved(session) is None:
                await self._save(session, Credential(client_id=client, host_id=host))

    # Using the plan -----------------------------------------------------------------

    async def access_token(self) -> str:
        """A fresh access token, renewed under the lock when it is in its last minute.
        Not signed in (or plan use not allowed): ``model_not_configured``. A refused
        refresh clears the tokens and fails as rejected credentials; any other failure
        keeps them and fails as a transient outage."""
        if not sign_in_enabled():
            raise LonoraError("model_not_configured", 409)
        saved = await self.credential()
        token = self._current(saved)
        if token is not None:
            return token
        failure: ModelProviderError | None = None
        async with self.db.sessions() as session, session.begin():
            await _lock(session, self.store.owner_id)
            saved = await self._saved(session)
            token = self._current(saved)
            if token is not None:
                return token
            assert saved is not None and saved.refresh_token is not None
            now = time.time()
            if saved.earliest_refresh_at and saved.earliest_refresh_at > now:
                if saved.expires_at > now:
                    return cast(str, saved.access_token)
                raise ModelProviderError(
                    FailureReason.OVERLOADED,
                    retry_after=saved.earliest_refresh_at - now,
                    provider_type="chatgpt_refresh_too_early",
                )
            try:
                keys = await self._keys()
                status, body = await self._call(
                    "POST",
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": saved.client_id,
                        "refresh_token": saved.refresh_token,
                        "resource": RESOURCE,
                    },
                )
            except (Unreachable, LonoraError):
                raise ModelProviderError(
                    FailureReason.CONNECTION, provider_type="chatgpt_refresh_unreachable"
                ) from None
            if status != 200:
                error = body.get("error")
                code: Any = (
                    cast(dict[str, Any], error).get("code") if isinstance(error, dict) else error
                )
                if code in TERMINAL_REFRESH:
                    await self._save(session, saved.cleared(sign_in_again=True))
                    failure = ModelProviderError(
                        FailureReason.AUTH, http_status=status, provider_type=cast(str, code)
                    )
                elif code == "invalid_client":
                    raise ModelProviderError(
                        FailureReason.AUTH, http_status=status, provider_type="invalid_client"
                    )
                else:
                    raise ModelProviderError(
                        FailureReason.OVERLOADED if status >= 429 else FailureReason.SERVER_ERROR,
                        http_status=status,
                        provider_type="chatgpt_refresh_failed",
                    )
            else:
                try:
                    tokens = self._tokens(body, saved)
                    if body.get("id_token") is not None:
                        subject, _ = self._identity(tokens["id_token"], saved.client_id, keys, None)
                        if subject != saved.subject:
                            raise ValueError()
                except (ValueError, LonoraError):
                    # The old refresh token was spent: it is never tried again.
                    await self._save(session, saved.cleared(sign_in_again=True))
                    failure = ModelProviderError(
                        FailureReason.AUTH, provider_type="chatgpt_refresh_unverified"
                    )
                else:
                    renewed = replace(saved, **tokens)
                    await self._save(session, renewed)
                    if not renewed.plan:
                        failure = ModelProviderError(
                            FailureReason.PERMISSION, provider_type="chatgpt_plan_use_off"
                        )
                    else:
                        token = renewed.access_token
        if failure is not None:
            # Committed first: the cleared tokens stand whatever the caller does next.
            raise failure
        return cast(str, token)

    @staticmethod
    def _current(saved: Credential | None) -> str | None:
        """The saved access token while it has more than a minute left; raises when there
        is nothing to use or renew."""
        if saved is None or not saved.access_token:
            if saved is not None and saved.sign_in_again:
                raise ModelProviderError(
                    FailureReason.AUTH, provider_type="chatgpt_sign_in_required"
                )
            raise LonoraError("model_not_configured", 409)
        if DIRECT_SCOPE not in saved.scopes:
            raise LonoraError("model_not_configured", 409)
        if saved.expires_at > time.time() + REFRESH_MARGIN:
            return saved.access_token
        return None

    async def keep_models_fresh(self, access_token: str) -> None:
        """Read the account's models again when the last read is 15 minutes old; a failed
        read keeps what was read before."""
        async with self.db.sessions() as session:
            plan = await SettingsRepository().get(session, PLAN_MODELS)
        last = max(float(plan.get("read_at") or 0), float(plan.get("tried_at") or 0))
        if not plan.get("subject") or time.time() - last < MODELS_SECONDS:
            return
        offered = await self._offered(access_token)
        async with self.db.sessions() as session, session.begin():
            settings = SettingsRepository()
            plan = await settings.get(session, PLAN_MODELS, fresh=True)
            update: dict[str, Any] = {"tried_at": time.time()}
            if offered is not None:
                update.update(offered=offered, read_at=time.time())
            await settings.put(session, PLAN_MODELS, {**plan, **update})

    async def refuse_model(self, model: str) -> None:
        """A model ChatGPT refused for this account at run time: hidden from its list until
        the next sign-in (OpenMausBot's refused models)."""
        async with self.db.sessions() as session, session.begin():
            await _lock(session, self.store.owner_id)
            saved = await self._saved(session)
            settings = SettingsRepository()
            plan = await settings.get(session, PLAN_MODELS, fresh=True)
            if saved is None or saved.subject is None or plan.get("subject") != saved.subject:
                return
            refused = list(plan.get("refused", []))
            if model not in refused:
                await settings.put(session, PLAN_MODELS, {**plan, "refused": [*refused, model]})

    # Sign-out -------------------------------------------------------------------------

    async def _revoke(self, saved: Credential) -> bool:
        """Revoke the renewable session at the ``revocation_endpoint`` OpenAI publishes;
        an HTTP 200 confirms it. One retry after a network failure or a 5xx."""
        try:
            status, discovery = await self._call("GET", DISCOVERY_URL)
        except Unreachable:
            return False
        endpoint = discovery.get("revocation_endpoint")
        if (
            status != 200
            or discovery.get("issuer") != ISSUER
            or not isinstance(endpoint, str)
            or urlsplit(endpoint).scheme != "https"
            or urlsplit(endpoint).netloc != urlsplit(ISSUER).netloc
        ):
            return False
        for _ in range(2):
            try:
                status, _body = await self._call(
                    "POST",
                    endpoint,
                    data={
                        "token": cast(str, saved.refresh_token),
                        "token_type_hint": "refresh_token",
                        "client_id": saved.client_id,
                    },
                )
            except Unreachable:
                continue
            if status < 500:
                return status == 200
        return False

    async def sign_out(self) -> dict[str, Any]:
        """Stop using the plan: revoke the session, then clear the tokens whatever OpenAI
        answered (the issued id and host stay). ``revoked`` says whether OpenAI confirmed."""
        async with self.db.sessions() as session, session.begin():
            await _lock(session, self.store.owner_id)
            saved = await self._saved(session)
            revoked = True
            if saved is not None and saved.refresh_token:
                revoked = await self._revoke(saved)
            if saved is not None:
                await self._save(session, saved.cleared(sign_in_again=False))
            await self._forget(session, PENDING)
            for key in (CONNECTION_SETTING + PROVIDER, PLAN_MODELS):
                row = await session.get(SettingRow, key)
                if row is not None:
                    await session.delete(row)
        if not revoked:
            log.warning("chatgpt_revocation_unconfirmed")
        return {"signed_out": True, "revoked": revoked}
