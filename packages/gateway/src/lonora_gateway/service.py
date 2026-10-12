import asyncio
from pathlib import Path

from lonora_agent.runtime import AgentRuntime
from lonora_db.client import Database
from lonora_db.owner import get_owner
from lonora_tools.loader import load_tools
from lonora_trading.reconciliation import reconcile_ambiguous

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
        self.identity = process_identity()
        self.stop = asyncio.Event()
        self.state = GatewayState.STARTING
        self.services: dict[str, OwnerServices] = {}
        self.runtime = AgentRuntime(load_tools(), lease_seconds, maximum_rounds)

    async def worker_loop(self) -> None:
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
            )
            if not claimed:
                await asyncio.sleep(self.poll_seconds)

    async def maintenance_loop(self) -> None:
        while not self.stop.is_set():
            await write_heartbeat(self.db, self.identity, self.state.value)
            await scheduler_tick(self.db)
            async with self.db.sessions() as session:
                owner = await get_owner(session)
            if owner:
                service = self.services.setdefault(
                    owner.id, OwnerServices.create(self.db, owner.id, self.key)
                )
                await dispatch_market_wakes(self.db, service.brokers)
                await reconcile_ambiguous(self.db, service.brokers)
            await asyncio.sleep(10)

    async def serve(self) -> None:
        self.state = GatewayState.RUNNING
        loops = [
            asyncio.create_task(supervise("worker-" + str(index), self.worker_loop, self.stop))
            for index in range(self.maximum_subagents + 1)
        ]
        loops.append(
            asyncio.create_task(supervise("maintenance", self.maintenance_loop, self.stop))
        )
        await self.stop.wait()
        self.state = GatewayState.DRAINING
        await write_heartbeat(self.db, self.identity, self.state.value)
        await drain(loops)
        for service in self.services.values():
            await service.close()
        self.state = GatewayState.STOPPED
        await write_heartbeat(self.db, self.identity, self.state.value)

    def request_stop(self) -> None:
        self.stop.set()
