"""Every tool call of a Run has its own id (P1-03).

Stored results, effect receipts and Trade Approval ids derive from the call id, so a
provider that sends an empty id, or repeats one within a reply or across rounds, would
answer a new call from an earlier call's record. The loop gives such a call a new id
before the reply is checkpointed; an id that is already unique is kept.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_providers.router import GlobalModelRouter
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from test_task_runtime import task_db as task_db
from test_tool_loop_execution import Arguments, Fixture, Script, conversation_run, saved_run


def turn(*calls: tuple[str, int]) -> ModelReply:
    return ModelReply(
        tool_calls=[
            ToolCall(id=identity, name="fixture_read", arguments={"n": n}) for identity, n in calls
        ]
    )


@pytest.mark.asyncio
async def test_an_empty_or_repeated_provider_id_never_answers_a_new_call(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executed: list[int] = []

    async def read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        executed.append(args["n"])
        # Oversized, so the result is stored under its call id (``store_result``).
        return {"n": args["n"], "page": "x" * 130_000}

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    model = Script(
        turn(("", 1), ("", 2)),
        turn(("call_0", 3), ("call_0", 4)),
        # The same id and the same arguments as a call two rounds back.
        turn(("call_0", 3)),
        turn(("unique-provider-id", 5)),
        ModelReply(text="Read five pages."),
    )
    context = replace(await conversation_run(task_db), artifact_root=tmp_path)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and run.result == "Read five pages.", run.error_code
    # Every proposed call ran: none was answered from another call's stored result.
    assert sorted(executed) == [1, 2, 3, 3, 4, 5]
    messages = [ModelMessage.model_validate(item) for item in run.execution_state["messages"]]
    proposed = [call.id for message in messages for call in message.tool_calls]
    answered = [message.tool_call_id for message in messages if message.role == "tool"]
    assert len(proposed) == 6 and all(proposed) and len(set(proposed)) == 6
    # The transcript stays valid: each call is answered once, in order.
    assert answered == proposed
    contents = [message.content for message in messages if message.role == "tool"]
    assert not any("tool_result_identity_conflict" in content for content in contents)
    # An id the provider made unique is kept, so earlier checkpoints still match.
    assert "unique-provider-id" in proposed and "call_0" in proposed
    # The checkpoint keeps the provider's own id of every call given a new one.
    kept = run.execution_state["provider_call_ids"]
    assert set(kept) == set(proposed) - {"call_0", "unique-provider-id"}
    assert sorted(kept.values()) == ["", "", "call_0", "call_0"]


@pytest.mark.asyncio
async def test_two_trades_with_one_provider_id_raise_two_trade_approvals() -> None:
    from check_streaming import Fixture as Api
    from test_proactive_wakes import database, retire, simulation

    database()
    fixture = await Api().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Two entries", supervised=True)
        thread = await fixture.conversation(agent)
        run = await fixture.run(agent, thread)

        class Router:
            """A provider that numbers its calls per reply: both trades are ``call_0``."""

            def __init__(self, credentials: Any) -> None:
                self.credentials = credentials

            async def complete(
                self,
                capability: Capability,
                messages: list[ModelMessage],
                tools: list[ToolDefinition],
                **_: Any,
            ) -> tuple[ModelReply, ModelSelection]:
                selection = ModelSelection(provider="openai", model="call-id-fixture")
                proposed = [
                    call
                    for message in messages
                    for call in message.tool_calls
                    if call.name == "trade_execute"
                ]
                if len(proposed) >= 2:
                    return ModelReply(text="Both entries are with the owner."), selection
                entry = {
                    "account_id": connection,
                    "symbol": "XAUUSD",
                    "action": "buy",
                    "volume": "0.1" if not proposed else "0.2",
                    "stop_loss": "95",
                    "tolerance": "1.5",
                    "reason": "Breakout above 100",
                }
                call = ToolCall(id="call_0", name="trade_execute", arguments=entry)
                return ModelReply(tool_calls=[call]), selection

        registry = load_tools()

        async def leased() -> ToolContext:
            context = await fixture.lease(run)
            return replace(
                context, router=cast(GlobalModelRouter, Router(context.router.credentials))
            )

        await execute_run(await leased(), registry, 30, 12)

        async def cards() -> list[dict[str, Any]]:
            shown = cast(
                list[dict[str, Any]],
                await fixture.request("GET", f"/trading/approvals?thread_id={thread['id']}"),
            )
            return [card for card in shown if card["run_id"] == run["id"]]

        first = await cards()
        assert len(first) == 1 and first[0]["status"] == "pending", first
        await fixture.request(
            "POST", f"/trading/approvals/{first[0]['id']}/decision", {"decision": "approve"}
        )
        await execute_run(await leased(), registry, 30, 12)
        both = await cards()
        # The second entry is a new card, never answered from the first one's record.
        assert len(both) == 2 and len({card["id"] for card in both}) == 2, both
        approved = next(card for card in both if card["id"] == first[0]["id"])
        assert approved["status"] == "completed", approved
        second = next(card for card in both if card["id"] != first[0]["id"])
        assert second["status"] == "pending"
        assert second["requests"][0]["volume"] == "0.2"
        stored = await fixture.request("GET", "/runs/" + run["id"])
        assert stored["status"] == "waiting_input", stored
    finally:
        await retire(fixture, connection)
        await fixture.close()
