"""MetaApi provisioning: create, deploy, undeploy, update and remove trading accounts.

Account-entity calls only. This client never opens an RPC or streaming connection and
never places an order: every order goes through the execution door (``MetaApiBroker``,
constructed only by ``BrokerManager`` and the connect check). It holds its own SDK
instance, so the trading instance's options are never changed, and it reuses the
process-wide transport patch as it is (every URL must still pass ``validate_sdk_url``).

SDK retries are off here as well: a retried ``create_account`` carries a new random
``transaction-id`` and would be a second account. MetaApi's long-running ``202`` wait
inside one call stays on. A create whose answer is lost is found again by ``find``.
"""

import importlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

import httpx
from lonora_core.error_logging import safe_exception_message
from lonora_core.user_error import LonoraError

from .metaapi import configure_sdk_transport

log = logging.getLogger("lonora.metaapi.provisioning")
PAGE = 1000
# Defaults for an account Lonora creates (recorded in the W-BROKER step 1 pull request).
RELIABILITY = "regular"
ACCOUNT_TYPE = "cloud-g2"
MAGIC = 0


@dataclass(frozen=True)
class ProvisionedAccount:
    """What MetaApi says about one account entity. No credential is ever kept here."""

    account_id: str
    login: str | None
    server: str | None
    platform: str | None
    region: str | None
    state: str | None
    connection_status: str | None

    @property
    def deployed(self) -> bool:
        return self.state == "DEPLOYED"

    @property
    def connected(self) -> bool:
        return self.connection_status == "CONNECTED"


def _field(entity: Any, name: str) -> str | None:
    try:
        value = getattr(entity, name, None)
    except (AttributeError, KeyError):
        # The SDK model reads its raw payload; a missing field is unknown, not an error.
        value = None
    return str(value).strip() if value is not None else None


def describe(entity: Any) -> ProvisionedAccount:
    version = _field(entity, "version")
    return ProvisionedAccount(
        account_id=str(entity.id),
        login=_field(entity, "login"),
        server=_field(entity, "server"),
        platform="mt" + version if version in {"4", "5"} else None,
        region=_field(entity, "region"),
        state=_field(entity, "state"),
        connection_status=_field(entity, "connection_status"),
    )


def _detail_codes(error: Exception) -> set[str]:
    details: Any = getattr(error, "details", None)
    items: list[Any] = cast(list[Any], details) if isinstance(details, list) else [details]
    codes: set[str] = set()
    for item in items:
        code = cast(dict[str, Any], item).get("code") if isinstance(item, dict) else None
        if code:
            codes.add(str(code))
    return codes


def provisioning_error(error: Exception) -> LonoraError:
    """Map an SDK failure to a code. Validation details are read for their code only."""
    if isinstance(error, LonoraError):
        return error
    status = getattr(error, "status_code", None)
    if status == 400:
        codes = _detail_codes(error)
        if "E_AUTH" in codes:
            return LonoraError("broker_password_rejected", 422)
        if "E_SRV_NOT_FOUND" in codes:
            return LonoraError("broker_server_not_found", 422)
        return LonoraError("broker_provisioning_rejected", 422)
    if status in {401, 403} or type(error).__name__ == "MethodAccessException":
        # MethodAccessException: an account access token, which cannot provision.
        return LonoraError("broker_token_rejected", 409)
    if status == 404:
        return LonoraError("broker_account_not_found", 404)
    if status == 409:
        return LonoraError("broker_provisioning_conflict", 409)
    if status == 429:
        return LonoraError("broker_rate_limited", 429)
    if (
        isinstance(error, (TimeoutError, httpx.TimeoutException))
        or "Timeout" in type(error).__name__
    ):
        return LonoraError("broker_provisioning_timeout", 504)
    return LonoraError("broker_provisioning_unavailable", 502)


class MetaApiProvisioning:
    def __init__(self, token: str):
        configure_sdk_transport()
        sdk: Any = importlib.import_module("metaapi_cloud_sdk")
        self.api: Any = sdk.MetaApi(
            token,
            {
                "requestTimeout": 60,
                "retryOpts": {"retries": 0, "longRunningRequestTimeoutInMinutes": 10},
                "enableSocketioDebugger": False,
                "packetLogger": {"enabled": False},
            },
        )
        self._redactions: tuple[str, ...] = (token,)

    def _failure(self, error: Exception, stage: str, secrets: Iterable[str] = ()) -> LonoraError:
        failure = provisioning_error(error)
        failure.diagnostic_type = type(error).__name__
        # The SDK message and URL only: validation details can echo request fields.
        failure.diagnostic_message = safe_exception_message(
            error, (*self._redactions, *(value for value in secrets if value))
        )
        log.warning(
            "broker_provisioning_%s_failed code=%s type=%s message=%s",
            stage,
            failure.code,
            failure.diagnostic_type,
            failure.diagnostic_message,
        )
        return failure

    async def _call(self, stage: str, secrets: Iterable[str], call: Any) -> Any:
        try:
            return await call()
        except Exception as error:
            # ``from None``: the SDK exception (and any request field it carries) stays
            # out of tracebacks; the diagnostic above is the redacted record.
            raise self._failure(error, stage, secrets) from None

    async def _entities(self, query: str | None, secrets: Iterable[str]) -> list[Any]:
        found: list[Any] = []
        offset = 0
        while True:
            accounts_filter: dict[str, Any] = {"offset": offset, "limit": PAGE}
            if query:
                accounts_filter["query"] = query
            listing = self.api.metatrader_account_api.get_accounts_with_infinite_scroll_pagination
            page = await self._call("list", secrets, partial(listing, accounts_filter))
            found.extend(page)
            if len(page) < PAGE:
                return found
            offset += PAGE

    async def _entity(self, account_id: str, secrets: Iterable[str] = ()) -> Any:
        return await self._call(
            "account",
            (account_id, *secrets),
            lambda: self.api.metatrader_account_api.get_account(account_id),
        )

    async def accounts(self) -> list[ProvisionedAccount]:
        return sorted(
            (describe(entity) for entity in await self._entities(None, ())),
            key=lambda account: account.account_id,
        )

    async def find(self, login: str, server: str) -> ProvisionedAccount | None:
        """The token's account with this exact login and server, deployed one first."""
        matches = sorted(
            (
                account
                for account in map(describe, await self._entities(login, (login,)))
                if account.login == login
                and (account.server or "").casefold() == server.strip().casefold()
            ),
            key=lambda account: (not account.deployed, account.account_id),
        )
        return matches[0] if matches else None

    async def default_region(self) -> str | None:
        """The region of an existing account of this token; None lets MetaApi choose."""
        regions = [account.region for account in await self.accounts() if account.region]
        return regions[0] if regions else None

    async def find_or_create(
        self, *, login: str, server: str, platform: str, password: str
    ) -> tuple[ProvisionedAccount, bool]:
        """Reuse the token's account for this login and server, or create one.

        Returns the account and whether it was created. The caller holds the owner's
        connection lock and persists the MetaApi id before it deploys.
        """
        if platform not in {"mt4", "mt5"}:
            raise LonoraError("broker_platform_required", 422)
        secrets = (login, password)
        existing = await self.find(login, server)
        if existing is not None:
            return existing, False
        region = await self.default_region()
        account: dict[str, Any] = {
            "login": login,
            "password": password,
            "server": server.strip(),
            "platform": platform,
            "name": "Lonora " + server.strip(),
            "magic": MAGIC,
            "reliability": RELIABILITY,
            "type": ACCOUNT_TYPE,
        }
        if region:
            account["region"] = region
        entity = await self._call(
            "create", secrets, lambda: self.api.metatrader_account_api.create_account(account)
        )
        return describe(entity), True

    async def state(self, account_id: str) -> ProvisionedAccount:
        return describe(await self._entity(account_id))

    async def _act(
        self, account_id: str, method: str, *arguments: Any, secrets: Iterable[str] = ()
    ) -> ProvisionedAccount:
        entity = await self._entity(account_id, secrets)
        await self._call(
            method, (account_id, *secrets), lambda: getattr(entity, method)(*arguments)
        )
        return describe(entity)

    async def deploy(self, account_id: str) -> ProvisionedAccount:
        return await self._act(account_id, "deploy")

    async def undeploy(self, account_id: str) -> ProvisionedAccount:
        return await self._act(account_id, "undeploy")

    async def redeploy(self, account_id: str) -> ProvisionedAccount:
        return await self._act(account_id, "redeploy")

    async def update_password(self, account_id: str, password: str) -> ProvisionedAccount:
        """Store a new password at MetaApi. It takes effect after a redeploy."""
        entity = await self._entity(account_id, (password,))
        # MetaApi's update replaces name and server too, so the current ones are sent.
        current = {key: _field(entity, key) for key in ("name", "server")}
        update = {**{key: value for key, value in current.items() if value}, "password": password}
        await self._call("update", (account_id, password), lambda: entity.update(update))
        return describe(entity)

    async def remove(self, account_id: str) -> None:
        await self._act(account_id, "remove")

    async def close(self) -> None:
        self.api.close()
