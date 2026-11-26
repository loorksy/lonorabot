"""Offline permission regression checks; no provider or broker connection."""

import json
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from lonora_agent.context.permissions import permission_context, permission_guidance
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.schema import AgentRow, RunRow, TradeApprovalRow
from lonora_trading import agent_permission, execution
from lonora_trading.authority_verdict import authority_verdict, verdict_sentence


@pytest.fixture(autouse=True)
def ask_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """These agents are in Ask: their requests go through the ladder and approvals."""
    monkeypatch.setattr(
        agent_permission,
        "acting_agent",
        AsyncMock(return_value=AgentRow(id="agent", role="specialist", trading_mode="ask")),
    )


def origin(trigger: str = "goal") -> RunRow:
    return RunRow(
        id="run",
        agent_id="agent",
        thread_id="chat",
        trigger=trigger,
        model_metadata={},
    )


def request(**changes: Any) -> TradeRequest:
    return TradeRequest.model_validate(
        {
            "account_id": "account",
            "symbol": "Exact.symbol#",
            "action": "buy",
            "volume": "0.1",
            "operation_id": "operation",
            **changes,
        }
    )


@pytest.mark.asyncio
async def test_a_run_from_removed_shadow_trading_never_runs_live():
    """Shadow trading is removed (Q57): its old Runs are refused, never live."""
    shadow_run = origin()
    shadow_run.model_metadata = {"execution_mode": "shadow"}
    with pytest.raises(LonoraError, match="shadow_execution_forbidden"):
        await execution.require_task_authority(AsyncMock(), shadow_run)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "level,grant,code",
    [
        ("analysis", None, "agent_analysis_only"),
        ("analysis", "signed-old", "agent_analysis_only"),
        ("supervised", "signed-old", "trade_approval_required"),
        # The ladder is monotonic: "On its own" without a covering grant asks like Ask me.
        ("autonomous", None, "trade_approval_required"),
    ],
)
async def test_executor_gate_rejects_authority_substitution(
    monkeypatch: pytest.MonkeyPatch, level: str, grant: str | None, code: str
):
    monkeypatch.setattr(agent_permission, "effective_permission", AsyncMock(return_value=level))
    session = AsyncMock()
    approved = [] if level == "autonomous" else [request().model_dump(mode="json")]
    session.scalars.return_value = [TradeApprovalRow(requests=approved)]
    with pytest.raises(LonoraError, match=code):
        await agent_permission.require_operation_permission(
            session, "owner", origin(), request(), grant
        )


@pytest.mark.asyncio
async def test_supervised_gate_matches_operation_identity_and_request(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        agent_permission, "effective_permission", AsyncMock(return_value="supervised")
    )
    session = AsyncMock()
    session.scalars.return_value = [TradeApprovalRow(requests=[request().model_dump(mode="json")])]
    await agent_permission.require_operation_permission(session, "owner", origin(), request(), None)
    for changed in [request(operation_id="retry"), request(volume="0.3")]:
        with pytest.raises(LonoraError, match="trade_approval_required"):
            await agent_permission.require_operation_permission(
                session, "owner", origin(), changed, None
            )


@pytest.mark.asyncio
async def test_autonomous_provisional_speech_requires_approval_and_signed_scope(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        agent_permission, "effective_permission", AsyncMock(return_value="autonomous")
    )
    monkeypatch.setattr(agent_permission, "provisional_voice", AsyncMock(return_value=True))
    session = AsyncMock()
    session.scalars.return_value = []
    with pytest.raises(LonoraError, match="trade_approval_required"):
        await agent_permission.require_operation_permission(
            session, "owner", origin(), request(), "grant"
        )
    session.scalars.return_value = [TradeApprovalRow(requests=[request().model_dump(mode="json")])]
    await agent_permission.require_operation_permission(
        session, "owner", origin(), request(), "grant"
    )
    # Outside every grant, the owner's exact approval admits the operation (monotonic
    # ladder); without it nothing is sent.
    await agent_permission.require_operation_permission(session, "owner", origin(), request(), None)
    session.scalars.return_value = []
    with pytest.raises(LonoraError, match="trade_approval_required"):
        await agent_permission.require_operation_permission(
            session, "owner", origin(), request(), None
        )


@pytest.mark.asyncio
async def test_direct_subagent_executor_path_cannot_inherit_authority(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(execution, "require_lease", AsyncMock(return_value=origin("subagent")))
    monkeypatch.setattr(execution, "acting_agent", AsyncMock())
    with pytest.raises(LonoraError, match="observe_only_execution_forbidden"):
        await execution.require_goal_lineage(
            AsyncMock(), Lease(run_id="run", owner="worker", fence=1), "owner"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ask", "full"])
@pytest.mark.parametrize("level", ["analysis", "supervised", "autonomous"])
@pytest.mark.parametrize("paused", [False, True])
@pytest.mark.parametrize("provisional", [False, True])
@pytest.mark.parametrize(
    "role,manages_all", [("specialist", False), ("specialist", True), ("personal", False)]
)
async def test_the_frame_verdict_is_what_the_door_does(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    level: str,
    paused: bool,
    provisional: bool,
    role: str,
    manages_all: bool,
):
    """For each kind of request the frame names, the door sends, asks or refuses with that
    code; the frame never tells a Full agent on provisional speech to wait for approval."""
    agent = AgentRow(
        id="agent", role=role, trading_mode=mode, paused=paused, manages_all_positions=manages_all
    )
    monkeypatch.setattr(agent_permission, "acting_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(agent_permission, "effective_permission", AsyncMock(return_value=level))
    monkeypatch.setattr(agent_permission, "provisional_voice", AsyncMock(return_value=provisional))
    monkeypatch.setattr(agent_permission, "ticket_agent", AsyncMock(return_value="another-agent"))
    session = AsyncMock()
    session.scalars.return_value = []  # No approved Trade Approval.
    verdict = authority_verdict(
        agent, cast(Any, level), provisional=provisional, observe_only=False
    )

    async def door(trade: TradeRequest, *, reducing: bool, grant: str | None = None) -> str:
        try:
            await agent_permission.require_operation_permission(
                session,
                "owner",
                origin(),
                trade,
                grant,
                reducing=reducing,
                target=MagicMock() if trade.position_id else None,
            )
        except LonoraError as error:
            if error.code == "trade_approval_required":
                return "needs_approval"
            return "refused:" + error.code
        return "execute"

    assert await door(request(), reducing=True) == verdict["reduce_risk"]
    if verdict["new_risk"] == "grant_or_approval":
        assert await door(request(), reducing=False, grant="grant") == "execute"
        assert await door(request(), reducing=False) == "needs_approval"
    else:
        assert await door(request(), reducing=False) == verdict["new_risk"]
    others = await door(request(action="close_position", position_id="ticket"), reducing=True)
    assert others == ("execute" if verdict["others_ticket"] == "lead" else verdict["others_ticket"])
    frame = permission_guidance(verdict, mode=mode, paused=paused, observe_only=False)
    assert all(verdict_sentence(kind, verdict[kind]) in frame for kind in verdict)
    if mode == "full" and level != "analysis" and not paused:
        assert verdict["new_risk"] == "execute"  # On provisional speech too.


@pytest.mark.asyncio
async def test_the_frame_reads_current_state_every_turn_and_carries_no_grant_data(
    monkeypatch: pytest.MonkeyPatch,
):
    from lonora_agent.context import permissions

    agent = AgentRow(id="agent", role="specialist", trading_mode="full", paused=False)
    level = AsyncMock(side_effect=["autonomous", "analysis", "supervised"])
    monkeypatch.setattr(permissions, "effective_permission", level)
    monkeypatch.setattr(permissions, "acting_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(permissions, "provisional_voice", AsyncMock(return_value=True))
    first = await permission_context(AsyncMock(), "owner", "agent", origin())
    resumed = await permission_context(AsyncMock(), "owner", "agent", origin())
    wake = origin()
    wake.model_metadata = {"authority": "observe_only"}
    observer = await permission_context(AsyncMock(), "owner", "agent", wake)
    facts = json.loads(first.split("<current_financial_permission>")[1].split("</")[0])
    assert facts == {"trading_mode": "full", "paused": False, "observe_only": False}
    # A Full agent on a provisional voice run executes; nothing tells it to wait.
    assert "A request that adds risk executes without a card." in first
    assert "agent_analysis_only" in resumed
    assert "observe_only_execution_forbidden" in observer and '"observe_only": true' in observer
    assert level.await_count == 3
    for text in (first, resumed, observer):
        assert not any(word in text for word in ("authorized_scopes", "signed", "global_trading"))
