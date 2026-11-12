"""A signed grant gets one restart-safe readiness review in the observe-only work lane.

Runs on a fresh migrated PostgreSQL database (LONORA_DATABASE_URL):

1. A bounded grant schedules exactly one observe-only review Run, even from two
   concurrent scheduler ticks. The review reads the account through the normal
   AgentRuntime, cannot trade (not even through a direct executor call), and stays
   quiet in the conversation: the owner already has the one confirmation line.
2. A grant with full management starts no task (the continuous task comes with Full mode,
   4.5.1) and gets no review.
3. A review the model cannot run is never retried and never puts the agent at "action
   required": it is observe-only and gates nothing. Its one review-scoped line stays only
   until a later Run of the agent completes.
4. The confirmation follows the conversation's language and is written once.
"""

import asyncio
import json
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

from check_device_authority import assistant_lines, bounded_grant, on_its_own, simulated_account
from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.collaboration.outcome_return import return_pending_outcomes
from lonora_agent.executor import execute_run
from lonora_bus.attention import attention_text
from lonora_contracts.domain import ThreadCreate
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.runs import RunRequest
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.activation_acknowledgment import acknowledge_grant
from lonora_db.activation_review import dispatch_activation_reviews
from lonora_db.runs import claim_next, create_run, run_data
from lonora_db.schema import (
    AccountAuthorityRow,
    EffectReceiptRow,
    MessageRow,
    RunRow,
    TicketRow,
    TradingJournalRow,
)
from lonora_db.threads import create_thread
from lonora_gateway.scheduler import scheduler_tick
from lonora_session.idempotency import stable_id
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

ALL_ACTIONS = [
    "buy",
    "sell",
    "buy_limit",
    "sell_limit",
    "buy_stop",
    "sell_stop",
    "close_position",
    "modify_position",
    "cancel_order",
    "modify_order",
]


async def claim_review(f: Fixture) -> dict[str, Any]:
    """Claim the review Run; a management Task's first Run may be queued in the lane too."""
    async with f.runtime.db.sessions() as session, session.begin():
        assert await claim_next(session, "activation-test", 120, lane="conversation") is None
        for _ in range(5):
            row = await claim_next(session, "activation-test", 120, lane="work")
            assert row
            if row.trigger == "activation":
                return run_data(row)
    raise AssertionError("no readiness review was queued")


async def main() -> None:
    f = await Fixture().open()
    try:
        account = await simulated_account(f, "activation-review")
        agent = await f.agent("Activation review", supervised=True)
        thread = await f.conversation(agent)
        assert await scheduler_tick(f.runtime.db) == 0
        device = await Device.enroll(f)
        grant = await device.sign_grant(
            f,
            await f.request(
                "POST",
                f"/agents/{agent['id']}/account-authorities",
                bounded_grant(thread["id"], account),
            ),
        )
        assert await on_its_own(f, agent["id"])
        counts = await asyncio.gather(scheduler_tick(f.runtime.db), scheduler_tick(f.runtime.db))
        assert sum(counts) == 1 and await dispatch_activation_reviews(f.runtime.db) == 0
        data = await claim_review(f)
        assert data["thread_id"] != thread["id"]
        context = await f.lease(data)
        async with f.runtime.db.sessions() as session:
            review = await session.get(RunRow, context.lease.run_id)
            assert review and review.model_metadata["account_authority_id"] == grant["id"]
            assert review.model_metadata["authority"] == "observe_only"
        # Even a direct executor caller cannot spend the grant from the review.
        try:
            await context.trading.execute(
                f.owner,
                TradeRequest(
                    operation_id="activation-must-not-trade",
                    account_id=account,
                    symbol="EURUSDm",
                    action="buy",
                    volume=Decimal("0.1"),
                ),
                context.lease,
                account_authority_id=grant["id"],
            )
        except LonoraError as error:
            assert error.code == "observe_only_execution_forbidden"
        else:
            raise AssertionError("the readiness review mutated the broker")
        phase = 0

        async def complete(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ) -> tuple[ModelReply, ModelSelection]:
            nonlocal phase
            assert capability == Capability.BACKGROUND
            assert "trade_execute" not in {tool.name for tool in tools}
            phase += 1
            if phase == 1:
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="activation-account",
                            name="account_read",
                            arguments={"account_id": account},
                        )
                    ]
                )
            else:
                result = json.loads(
                    next(
                        message.content
                        for message in reversed(messages)
                        if message.role == "tool" and message.tool_call_id == "activation-account"
                    )
                )
                assert result["ok"] is True and result["account"]["balance"] == "2500"
                reply = ModelReply(
                    text="Reviewed the account inside the signed grant. Waiting for current "
                    "market evidence; no trade was sent."
                )
            return reply, ModelSelection(provider="openai", model="scripted-activation-review")

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 5)
        assert phase == 2
        async with f.runtime.db.sessions() as session:
            completed = await session.get(RunRow, context.lease.run_id)
            assert completed and completed.status == "completed"
        await return_pending_outcomes(f.runtime.db)
        await return_pending_outcomes(f.runtime.db)
        assert await assistant_lines(f, thread["id"]) == [attention_text("grant_activated", "ar")]
        async with f.runtime.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        assert await scheduler_tick(f.runtime.db) == 0
        print(
            "PASS a bounded grant schedules one restart-safe observe-only review; it reads the "
            "account, cannot trade and stays quiet behind the single confirmation line"
        )

        # Full management of a whole account is the Personal Agent's grant card.
        agents = cast(list[dict[str, Any]], await f.request("GET", "/agents"))
        manager = next(row for row in agents if row["role"] == "personal")
        manager_thread = await f.conversation(manager)
        full = await device.sign_grant(
            f,
            await f.request(
                "POST",
                f"/agents/{manager['id']}/account-authorities",
                {
                    "thread_id": manager_thread["id"],
                    "account_id": account,
                    "management_mode": "full",
                    "symbol_scope": "account",
                    "symbols": [],
                    "actions": ALL_ACTIONS,
                },
            ),
        )
        assert await dispatch_activation_reviews(f.runtime.db) == 0
        async with f.runtime.db.sessions() as session:
            receipt = await session.get(EffectReceiptRow, "activation-review:" + full["id"])
            task = await session.get(TicketRow, stable_id(full["id"], "account-management-task"))
            assert receipt and receipt.result == {"skipped": "management_task"}
            # A grant starts no task: the continuous task comes with Full mode (4.5.1).
            assert task is None
            assert await session.get(RunRow, stable_id(full["id"], "activation-review")) is None
        print("PASS a full-management grant starts no task and gets no extra review")

        unconfigured = await f.agent("Unconfigured review", supervised=True)
        unconfigured_thread = await f.conversation(unconfigured)
        await device.sign_grant(
            f,
            await f.request(
                "POST",
                f"/agents/{unconfigured['id']}/account-authorities",
                bounded_grant(unconfigured_thread["id"], account),
            ),
        )
        assert await scheduler_tick(f.runtime.db) == 1
        failed_context = await f.lease(await claim_review(f))

        async def unavailable(*args: Any, **kwargs: Any) -> Any:
            raise LonoraError("model_not_configured", 409)

        with patch.object(failed_context.router, "complete", unavailable):
            await execute_run(failed_context, load_tools(), 120, 5)
        live = await f.request("GET", f"/agents/{unconfigured['id']}/state")
        assert live["state"] != "action_required", live
        assert live["reason_code"] is None, live
        assert live["account_authorities"][0]["review_status"] == "failed"
        await return_pending_outcomes(f.runtime.db)
        # The review produced no result to report; the inbox state carries the failure.
        assert await assistant_lines(f, unconfigured_thread["id"]) == [
            attention_text("grant_activated", "ar")
        ]
        assert await scheduler_tick(f.runtime.db) == 0  # No paid-model retry loop.
        # Later work of the agent completes: the old review failure is history, not status.
        async with f.runtime.db.sessions() as session, session.begin():
            later = await create_run(
                session,
                f.owner,
                RunRequest(
                    agent_id=unconfigured["id"], thread_id=unconfigured_thread["id"], prompt="x"
                ),
                stable_id(unconfigured["id"], "later-work"),
            )
            later.status = "completed"
        live = await f.request("GET", f"/agents/{unconfigured['id']}/state")
        assert live["state"] != "action_required", live
        assert live["account_authorities"][0]["review_status"] == "superseded", live
        print(
            "PASS a review the model cannot run is not retried, adds no chat noise beyond the "
            "confirmation, never needs the owner and its line ends once later work completes"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            english = await create_thread(session, f.owner, ThreadCreate(agent_id=agent["id"]))
            session.add(
                MessageRow(
                    thread_id=english.id,
                    seq=english.next_seq,
                    role="user",
                    content="Please let this agent trade EURUSD on its own",
                )
            )
            english.next_seq += 1
            english_id = english.id
        await device.sign_grant(
            f,
            await f.request(
                "POST",
                f"/agents/{agent['id']}/account-authorities",
                bounded_grant(english_id, account),
            ),
        )
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.scalar(
                select(AccountAuthorityRow).where(
                    AccountAuthorityRow.thread_id == english_id,
                    AccountAuthorityRow.status == "active",
                )
            )
            assert row
            await acknowledge_grant(session, row)
            await acknowledge_grant(session, row)
        assert await assistant_lines(f, english_id) == [attention_text("grant_activated", "en")]
        async with f.runtime.db.sessions() as session:
            first = await session.get(AccountAuthorityRow, grant["id"], populate_existing=True)
            # Signing again on the same account replaces the earlier grant.
            assert first and first.status == "revoked"
        devices = cast(list[dict[str, Any]], await f.request("GET", "/auth/devices"))
        for item in devices:
            await f.request("DELETE", "/auth/devices/" + item["id"])
        assert not await on_its_own(f, agent["id"])
        assert not await on_its_own(f, manager["id"])
        print(
            "PASS the confirmation line follows the conversation's language and is written once; "
            "revoking the device ends trading on its own"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
