import asyncio
from pathlib import Path

from lonora_agent.collaboration.outcome_return import return_pending_outcomes
from lonora_agent.runtime import AgentRuntime
from lonora_charts.runtime import chart_runtime_tick
from lonora_db.client import Database
from lonora_db.owner import get_owner
from lonora_tools.loader import load_tools
from lonora_trading.reconciliation import reconcile_ambiguous

from .connection_manager import close_connections, maintain_voice
from .event_dispatch import dispatch_channels
from .heartbeat import write_heartbeat
from .lifecycle import GatewayState
from .process_identity import process_identity
from .run_dispatch import dispatch_one
from .runtime import OwnerServices
from .scheduler import scheduler_tick
from .shutdown import drain
from .supervisor import supervise
from .wake_dispatch import dispatch_market_wakes


class Gateway:
    def __init__(
        self,
        db: Database,
        key: str,
        artifact_root: Path,
        lease_seconds: int = 120,
        maximum_rounds: int = 24,
        maximum_subagents: int = 4,
        poll_seconds: float = 0.5,
    ):
        self.db, self.key, self.root = db, key, artifact_root
        self.lease_seconds, self.maximum_subagents, self.poll_seconds = (
            lease_seconds,
            maximum_subagents,
            poll_seconds,
        )
        self.voice_tasks: dict[str, asyncio.Task[None]] = {}
        self.identity = process_identity()
        self.stop = asyncio.Event()
        self.state = GatewayState.STARTING
        self.services: dict[str, OwnerServices] = {}
        self.runtime = AgentRuntime(load_tools(), lease_seconds, maximum_rounds)

    async def worker_loop(self, lane: str | None = None) -> None:
        while not self.stop.is_set():
            claimed = await dispatch_one(
                self.db,
                self.identity,
                self.runtime,
                self.services,
                self.key,
                self.root,
                self.lease_seconds,
                self.maximum_subagents,
                lane,
            )
            if not claimed:
                await asyncio.sleep(self.poll_seconds)

    async def maintenance_loop(self) -> None:
        while not self.stop.is_set():
            await write_heartbeat(self.db, self.identity, self.state.value)
            await scheduler_tick(self.db)
            await return_pending_outcomes(self.db)
            async with self.db.sessions() as session:
                owner = await get_owner(session)
            if owner:
                if owner.id not in self.services:
                    self.services[owner.id] = OwnerServices.create(self.db, owner.id, self.key)
                service = self.services[owner.id]
                await reconcile_ambiguous(self.db, service.brokers)
                from lonora_trading.broker_recovery import maintenance_account_recovery

                await maintenance_account_recovery(self.db, service.brokers, owner.id)
                from lonora_trading.goals import recover_goals

                await recover_goals(self.db)
                from lonora_trading.opportunities import maintenance_opportunities

                await maintenance_opportunities(self.db, owner.id)
            await asyncio.sleep(10)

    async def market_loop(self) -> None:
        while not self.stop.is_set():
            for service in list(self.services.values()):
                await service.market.maintain()
                from lonora_trading.shadow import advance_shadow

                await advance_shadow(self.db, service.brokers, service.owner_id)
            await asyncio.sleep(2)

    async def charts_loop(self) -> None:
        while not self.stop.is_set():
            for service in list(self.services.values()):
                await chart_runtime_tick(
                    self.db,
                    service.brokers,
                    service.owner_id,
                    self.identity,
                    maintain_streams=False,
                )
            await asyncio.sleep(2)

    async def watches_loop(self) -> None:
        while not self.stop.is_set():
            for service in list(self.services.values()):
                await dispatch_market_wakes(self.db, service.brokers)
            await asyncio.sleep(2)

    async def voice_loop(self) -> None:
        while not self.stop.is_set():
            for service in list(self.services.values()):
                await maintain_voice(self.db, service, self.identity, self.voice_tasks)
            await asyncio.sleep(0.5)

    async def channels_loop(self) -> None:
        while not self.stop.is_set():
            for service in list(self.services.values()):
                await dispatch_channels(self.db, service)
            await asyncio.sleep(2)

    async def serve(self) -> None:
        self.state = GatewayState.RUNNING
        loops = [
            asyncio.create_task(supervise("worker-" + str(index), self.worker_loop, self.stop))
            for index in range(self.maximum_subagents + 1)
        ]

        async def foreground() -> None:
            await self.worker_loop("conversation")

        loops.append(asyncio.create_task(supervise("conversation", foreground, self.stop)))
        loops.append(
            asyncio.create_task(supervise("maintenance", self.maintenance_loop, self.stop))
        )
        loops.append(asyncio.create_task(supervise("channels", self.channels_loop, self.stop)))
        loops.append(asyncio.create_task(supervise("voice", self.voice_loop, self.stop)))
        loops.append(asyncio.create_task(supervise("market", self.market_loop, self.stop)))
        loops.append(asyncio.create_task(supervise("charts", self.charts_loop, self.stop)))
        loops.append(asyncio.create_task(supervise("watches", self.watches_loop, self.stop)))
        await self.stop.wait()
        self.state = GatewayState.DRAINING
        await write_heartbeat(self.db, self.identity, self.state.value)
        await drain(loops)
        await close_connections(self.services, self.voice_tasks)
        self.state = GatewayState.STOPPED
        await write_heartbeat(self.db, self.identity, self.state.value)

    def request_stop(self) -> None:
        self.stop.set()
