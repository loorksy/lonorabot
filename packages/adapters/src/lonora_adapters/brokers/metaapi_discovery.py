"""Bounded discovery shared by historical REST and websocket SDK consumers."""

import asyncio
import logging
from datetime import datetime
from typing import Any, cast

from lonora_core.error_logging import safe_exception_message
from lonora_core.user_error import LonoraError

from .metaapi_lifecycle import ConnectionSlot

DISCOVERY_TIMEOUT_SECONDS = 30
log = logging.getLogger("lonora.metaapi")


async def update_domain(client: Any) -> None:
    """Replace the SDK's cancellable bare Future with one shielded owner task.

    No broker operation is replayed here: this request only discovers API hosts.
    SDK-created stale/abandoned requestPromise values are deliberately not awaited.
    """
    cache = client._url_cache
    if cache.get("domain") and cache.get("lastUpdated", 0) >= datetime.now().timestamp() - 600:
        return
    slot = getattr(client, "_lonora_domain_slot", None)
    if slot is None:
        slot = ConnectionSlot("discovery")
        client._lonora_domain_slot = slot

    async def refresh() -> None:
        try:
            async with asyncio.timeout(DISCOVERY_TIMEOUT_SECONDS):
                settings = await client._http_client.request(
                    {
                        "url": f"https://mt-provisioning-api-v1.{client._domain}"
                        "/users/current/servers/mt-client-api",
                        "method": "GET",
                        "headers": {"auth-token": client._token},
                    },
                    "_update_domain",
                )
            if not isinstance(settings, dict):
                raise ValueError("Broker discovery returned invalid settings")
            values = cast(dict[str, Any], settings)
            if any(
                not isinstance(values.get(field), str) or not values[field]
                for field in ("domain", "hostname")
            ):
                raise ValueError("Broker discovery returned invalid settings")
            updated: dict[str, Any] = {
                "domain": values["domain"],
                "hostname": values["hostname"],
                "requestPromise": None,
                "lastUpdated": datetime.now().timestamp(),
            }
            client._url_cache = updated
            client._retry_interval_in_seconds = 1
            slot.ready()
        except (Exception, asyncio.CancelledError) as error:
            task = asyncio.current_task()
            if isinstance(error, asyncio.CancelledError) and task is not None and task.cancelling():
                raise
            failure = LonoraError(
                "broker_connection_timeout"
                if isinstance(error, TimeoutError)
                else "broker_connection_unavailable",
                504 if isinstance(error, TimeoutError) else 502,
            )
            failure.diagnostic_type = type(error).__name__
            failure.diagnostic_message = (
                "Broker discovery transport was cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "Broker discovery timed out"
                if isinstance(error, TimeoutError)
                else safe_exception_message(error, (client._token,))
            )
            slot.failed(failure)
            log.warning(
                "broker_discovery_failed code=%s type=%s message=%s",
                failure.code,
                failure.diagnostic_type,
                failure.diagnostic_message,
            )
            raise failure from error
        finally:
            client._url_cache["requestPromise"] = None

    await slot.get(refresh)
