import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.chart import ChartState
from lonora_contracts.runs import Lease
from lonora_core.chart_annotations import protect_agent_annotations
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.cloud_charts import CloudChartRepository
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, ThreadRow
from lonora_db.transactions import resource_data
from sqlalchemy.ext.asyncio import AsyncSession

from .runtime import refresh_chart, refresh_identity


@dataclass(frozen=True)
class ChartCommand:
    """One native chart command; a lease fence is deliberately not its identity."""

    owner_id: str
    agent_id: str
    thread_id: str
    run_id: str
    call_id: str
    tool: str
    arguments: dict[str, Any]

    @property
    def key(self) -> str:
        return (
            "chart-command:" + sha256(json.dumps([self.run_id, self.call_id]).encode()).hexdigest()
        )

    @property
    def digest(self) -> str:
        return sha256(
            json.dumps(
                {
                    "kind": "chart-command-v1",
                    "owner_id": self.owner_id,
                    "agent_id": self.agent_id,
                    "thread_id": self.thread_id,
                    "run_id": self.run_id,
                    "call_id": self.call_id,
                    "tool": self.tool,
                    "arguments": self.arguments,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()


async def _command_result(
    session: AsyncSession, command: ChartCommand, lease: Lease
) -> dict[str, Any] | None:
    run = await require_lease(session, lease, lock=True)
    thread = await session.get(ThreadRow, run.thread_id)
    if (
        not command.call_id
        or command.run_id != lease.run_id
        or run.agent_id != command.agent_id
        or run.thread_id != command.thread_id
        or thread is None
        or thread.owner_id != command.owner_id
    ):
        raise LonoraError("chart_command_scope_mismatch", 409)
    receipt = await session.get(EffectReceiptRow, command.key)
    if receipt is None:
        return None
    if (
        receipt.result.get("kind") != "chart-command-v1"
        or receipt.result.get("digest") != command.digest
    ):
        raise LonoraError("chart_command_identity_conflict", 409)
    return cast(dict[str, Any], receipt.result["acknowledgment"])


async def replay_chart_command(
    db: Database, command: ChartCommand, lease: Lease
) -> dict[str, Any] | None:
    async with db.sessions() as session, session.begin():
        return await _command_result(session, command, lease)


def stored_scene(data: dict[str, Any], version: int) -> dict[str, Any]:
    if data.get("scene_revision") != version:
        raise LonoraError("chart_initializing", 409)
    if data.get("scene_status") != "ready":
        raise LonoraError(str(data.get("error_code") or "chart_data_unavailable"), 409)
    scene = data.get("scene")
    if not isinstance(scene, dict):
        raise LonoraError("chart_initializing", 409)
    return cast(dict[str, Any], scene)


async def load_chart_state(db: Database, owner_id: str, chart_id: str) -> ChartState:
    async with db.sessions() as session:
        row = await CloudChartRepository().get(session, owner_id, chart_id)
        return ChartState.model_validate(row.payload)


async def inspect_chart(db: Database, owner_id: str, chart_id: str) -> dict[str, Any]:
    async with db.sessions() as session:
        row = await CloudChartRepository().get(session, owner_id, chart_id)
        chart = resource_data(row)
        try:
            scene = stored_scene(row.state, row.version)
        except LonoraError as error:
            return {"chart": chart, "scene": None, "code": error.code}
        return {"chart": chart, "scene": scene}


async def create_chart(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    state: ChartState,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
    resource_id: str | None = None,
    lease: Lease | None = None,
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        row = await session.get(CloudChartRepository.row_type, resource_id) if resource_id else None
        if row is not None:
            if row.owner_id != owner_id:
                raise LonoraError("cloud_charts_not_found", 404)
        else:
            row = await CloudChartRepository().create(
                session,
                owner_id,
                state.model_dump(mode="json"),
                agent_id=agent_id,
                thread_id=thread_id,
                resource_id=resource_id,
            )
        chart_id = row.id
    await refresh_chart(db, brokers, owner_id, chart_id, refresh_identity(), lease, force=True)
    return await inspect_chart(db, owner_id, chart_id)


async def update_chart(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    chart_id: str,
    version: int,
    state: ChartState,
    lease: Lease | None = None,
    actor_agent_id: str | None = None,
    command: ChartCommand | None = None,
) -> dict[str, Any]:
    acknowledgment: dict[str, Any] | None = None
    async with db.sessions() as session, session.begin():
        if command:
            if (
                lease is None
                or command.owner_id != owner_id
                or command.agent_id != actor_agent_id
                or command.arguments.get("chart_id") != chart_id
                or command.arguments.get("version") != version
            ):
                raise LonoraError("chart_command_scope_mismatch", 409)
            prior = await _command_result(session, command, lease)
            if prior is not None:
                return prior
        elif lease:
            await require_lease(session, lease, lock=True)
        if actor_agent_id:
            previous = await CloudChartRepository().get(session, owner_id, chart_id, lock=True)
            if previous.version != version:
                raise LonoraError("version_conflict", 409)
            protect_agent_annotations(
                previous.payload.get("annotations", []), state.annotations, actor_agent_id
            )
        row = await CloudChartRepository().update(
            session, owner_id, chart_id, state.model_dump(mode="json"), version
        )
        if command:
            # Configuration acknowledgment only. Never freeze quotes/candles as current evidence.
            acknowledgment = {
                "chart": {
                    "id": row.id,
                    "version": row.version,
                    "payload": row.payload,
                    "state": {},
                },
                "scene": None,
                "command": {"status": "applied", "tool": command.tool, "revision": row.version},
                "requires_scene_inspection": True,
            }
            session.add(
                EffectReceiptRow(
                    key=command.key,
                    result={
                        "kind": "chart-command-v1",
                        "digest": command.digest,
                        "acknowledgment": acknowledgment,
                    },
                )
            )
    if acknowledgment is not None:
        # Repository updates already notify the gateway; refresh failure cannot undo the command.
        return acknowledgment
    await refresh_chart(db, brokers, owner_id, chart_id, refresh_identity(), lease, force=True)
    return await inspect_chart(db, owner_id, chart_id)
