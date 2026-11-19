"""The Gateway's side of the broker relay (``lonora_db.broker_relay``).

The Gateway alone keeps MetaApi connections. Each request the API process wrote is
claimed once and answered with this Gateway's own adapter: a read, or an owner's direct
order run by the Gateway's ``ExecutionService`` (its journal, checks and send unchanged).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from lonora_adapters.brokers.relay import READS, perform
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.broker_relay import RelayRequest, answer, claim, prune
from lonora_db.client import Database

from .runtime import OwnerServices

log = logging.getLogger(__name__)
PRUNE_SECONDS = 300


class BrokerRelay:
    def __init__(self, db: Database, service: Callable[[str], OwnerServices]):
        self.db, self.service = db, service
        self.tasks: set[asyncio.Task[None]] = set()
        self.pruned_at = 0.0

    async def iteration(self) -> None:
        for request in await claim(self.db):
            task = asyncio.create_task(self.serve(request), name="broker-relay:" + request.kind)
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        if time.monotonic() - self.pruned_at >= PRUNE_SECONDS:
            await prune(self.db)
            self.pruned_at = time.monotonic()

    async def serve(self, request: RelayRequest) -> None:
        try:
            result = await self.perform(request)
        except LonoraError as failure:
            await answer(self.db, request.id, error=failure)
        except Exception as error:  # noqa: BLE001 - the asker gets a code, never a trace
            log.warning("broker_relay_failed kind=%s type=%s", request.kind, type(error).__name__)
            await answer(
                self.db, request.id, error=LonoraError("broker_connection_unavailable", 502)
            )
        else:
            await answer(self.db, request.id, result)

    async def perform(self, request: RelayRequest) -> Any:
        services = self.service(request.owner_id)
        if request.kind == "execute":
            order = TradeRequest.model_validate(request.arguments)
            if order.account_id != request.connection_id:
                raise LonoraError("broker_relay_invalid", 400)
            result = await services.trading.execute(request.owner_id, order)
            return result.model_dump(mode="json")
        if request.kind not in READS:
            raise LonoraError("broker_relay_invalid", 400)
        broker = await services.brokers.get(request.owner_id, request.connection_id)
        return await perform(broker, request.kind, request.arguments)
