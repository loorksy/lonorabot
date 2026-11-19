"""Owner action cards: classification, proposal validation and the authority path.

The end-to-end card journeys (tool, runtime cards, owner decisions with a passkey) run
on PostgreSQL in ``tests/check_owner_actions.py``. These tests pin the pure rules and
that no tool can reach a decision.
"""

import ast
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.attention import ATTENTION_KINDS, classify_attention
from lonora_db.client import Database
from lonora_db.obligations import prepare_delete
from lonora_db.owner_actions import (
    confirm_in_thread,
    create_card,
    owner_action_data,
    propose,
    settle,
)
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    BrokerSessionRow,
    MessageRow,
    OwnerActionRow,
    RunRow,
    ThreadRow,
    TradingJournalRow,
)
from lonora_gateway.liveness import Liveness
from lonora_gateway.watchdog import Watchdog
from lonora_tools.loader import load_tools
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
ROOT = Path(__file__).resolve().parents[1]


def test_an_ambiguous_operation_is_one_action_required_item_per_operation() -> None:
    ambiguous = classify_attention(
        "trading.operation_updated",
        {"operation_id": "op-1", "account_id": "acct", "status": "ambiguous", "transition_id": "x"},
    )
    assert (ambiguous.importance, ambiguous.code) == ("action_required", "operation_uncertain")
    # Keyed by the operation, not the account, and stable across rewrites of the row.
    assert ambiguous.resource_id == "op-1" and ambiguous.transition == "ambiguous"
    for status in ("reserved", "submitted", "confirmed", "resolved", "failed"):
        quiet = classify_attention(
            "trading.operation_updated", {"operation_id": "op-1", "status": status}
        )
        assert quiet.importance == "silent", status
    assert "trading.operation_updated" in ATTENTION_KINDS
    assert "trading.controls_updated" not in ATTENTION_KINDS
    assert not {kind for kind in ATTENTION_KINDS if kind.startswith("trading.restriction")}


def test_a_stored_lift_card_could_not_be_read_back_and_its_tools_are_gone() -> None:
    # Why migration 0086 deletes stored lift_restriction cards (14.3.9): the contract
    # refuses the kind, and no tool creates or lists a restriction any more.
    with pytest.raises(ValidationError):
        OwnerActionProposal.model_validate({"kind": "lift_restriction", "restriction_id": "r1"})
    assert not {"trade_restriction_create", "trade_restriction_list"} & set(load_tools().tools)


@pytest.mark.parametrize(
    "arguments",
    [
        {"kind": "resolve_operation", "operation_id": "op", "account_id": "a"},
        {"kind": "grant_authority", "all_pairs": True, "symbols": ["XAUUSD"]},
        {"kind": "grant_authority", "actions": ["buy", "buy"]},
        {"kind": "grant_authority", "title": "Sign everything"},
    ],
)
def test_a_proposal_carries_only_the_fields_of_its_kind(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        OwnerActionProposal.model_validate(arguments)


def test_agents_can_only_propose_and_the_decision_is_an_owner_session_route() -> None:
    registry = load_tools()
    names = sorted(name for name in registry.tools if name.startswith("owner_action"))
    assert names == ["owner_action_propose"]
    tool = registry.tools["owner_action_propose"]
    assert not tool.financial and not tool.read_only and tool.replay_safe
    assert tool.toolset == "trading" and not tool.eager
    # No tool module imports anything that settles or decides a card (owner_action_propose
    # reads the actions for a grant card). agent_create raises
    # a creation card or a creation's Undo card, supervision_change a supervision card, its
    # Undo card or a Restore card; credential cards come from a proposal; none settles
    # one. Trusting a source raises no card (VISION 10.3.2).
    allowed = {
        "ALL_ACTIONS",
        "card_facts",
        "live_status",
        "propose",
        "account_facts",
        "lock_owner_actions",
        "payload_hash",
        "pending_effect",
        "propose_creation",
        "raise_created_card",
        "propose_supervision",
        "raise_supervision_card",
        "raise_supervision_stopped_card",
        # broker_connect raises the server-built broker Secret card (9.2); it settles nothing.
        "propose_effect",
    }
    for path in (ROOT / "packages/tools/src/lonora_tools").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module == "lonora_db.owner_actions":
                assert {alias.name for alias in node.names} <= allowed, path
            if isinstance(node, ast.ImportFrom) and node.module and "routes" in node.module:
                raise AssertionError(f"{path} imports an API route")
    from fastapi.routing import APIRoute
    from lonora_api.app import ROUTES
    from lonora_api.middleware.auth import require_owner
    from lonora_api.routes.owner_actions import router

    assert "owner_actions" in ROUTES
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert {route.path for route in routes} == {
        "/owner-actions",
        "/owner-actions/{card_id}/challenge",
        "/owner-actions/{card_id}/decision",
        # «طلب جديد»: a fresh card for an expired one; it decides nothing.
        "/owner-actions/{card_id}/renew",
    }
    for route in routes:
        assert any(item.call is require_owner for item in route.dependant.dependencies), route


async def owned_account(db: Database, owner: str) -> str:
    async with db.sessions() as session, session.begin():
        row = BrokerSessionRow(owner_id=owner, payload={"provider": "simulation"})
        session.add(row)
        await session.flush()
        return row.id


@pytest.mark.asyncio
async def test_a_card_sits_after_the_conversation_and_expires_without_a_scheduler(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    change = OwnerActionProposal(kind="connect_credential", target="news_feed")
    async with db.sessions() as session, session.begin():
        conversation = await session.get(ThreadRow, thread)
        assert conversation is not None
        row, created = await propose(
            session, owner, change, card_id="call-2", agent_id=agent, thread_id=thread, run_id=None
        )
        assert created and row.timeline_seq == conversation.next_seq
        row.expires_at = utcnow() - timedelta(seconds=1)
        assert (await owner_action_data(session, row))["status"] == "expired"
        replaced, created = await propose(
            session, owner, change, card_id="call-3", agent_id=agent, thread_id=thread, run_id=None
        )
        assert created and replaced.id != row.id
        stored = await session.get(OwnerActionRow, row.id)
        assert stored is not None and stored.status == "expired"


async def ack(session: AsyncSession, card: OwnerActionRow) -> MessageRow:
    await settle(session, card, "confirmed", None, via="tap", result=card.result)
    await confirm_in_thread(session, card)
    message = await session.scalar(
        select(MessageRow)
        .where(MessageRow.thread_id == card.thread_id, MessageRow.role == "assistant")
        .order_by(MessageRow.seq.desc())
        .limit(1)
    )
    assert message is not None
    return message


async def say(session: AsyncSession, thread: ThreadRow, content: str) -> None:
    session.add(MessageRow(thread_id=thread.id, seq=thread.next_seq, role="user", content=content))
    thread.next_seq += 1
    await session.flush()


@pytest.mark.asyncio
async def test_the_confirmation_line_says_what_still_holds_new_risk(task_db: Fixture) -> None:
    db, owner, agent, thread_id = task_db
    account = await owned_account(db, owner)
    async with db.sessions() as session, session.begin():
        english = await session.get(ThreadRow, thread_id)
        assert english is not None
        await say(session, english, "Did the gold trade go through?")
        # An answered trade releases its own hold; another uncertain one there still holds.
        for identifier in ("op-answered", "op-other"):
            session.add(
                TradingJournalRow(
                    operation_id=identifier,
                    owner_id=owner,
                    account_id=account,
                    request_hash="h",
                    request={"symbol": "GBPUSD"},
                    status="ambiguous" if identifier == "op-other" else "resolved",
                    result={},
                )
            )
        await session.flush()
        answer = await create_card(
            session,
            owner,
            card_id="resolve-answered",
            agent_id=agent,
            thread=english,
            run_id=None,
            source="system",
            kind="resolve_operation",
            subject="operation:op-answered",
            payload={"operation_id": "op-answered"},
        )
        answer.result = {"outcome": "unknown"}
        held = await ack(session, answer)
        assert held.content == (
            "Recorded: the outcome stays unknown. It will not be resent and no longer holds new "
            "risk on that market. A trade without a confirmed broker result still holds new risk "
            "there."
        )


@pytest.mark.asyncio
async def test_a_delete_supersedes_its_cards_and_a_gone_agent_never_blocks_the_tap(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread_id = task_db
    account = await owned_account(db, owner)
    async with db.sessions() as session, session.begin():
        group = ThreadRow(owner_id=owner, agent_id=None, title="Desk")
        helper = AgentRow(owner_id=owner, name="Helper")
        other = AgentRow(owner_id=owner, name="Other")
        session.add_all([group, helper, other])
        await session.flush()
        conversation = await session.get(ThreadRow, thread_id)
        assert conversation is not None

        async def card(card_id: str, thread: ThreadRow, kind: str, by: str) -> OwnerActionRow:
            payload: dict[str, Any] = (
                {"spec": {"account_id": account}}
                if kind == "create_agent"
                else {"target": "news_feed", "service": None}
            )
            return await create_card(
                session,
                owner,
                card_id=card_id,
                agent_id=by,
                thread=thread,
                run_id=None,
                source="agent",
                kind=kind,
                subject="agent-create" if kind == "create_agent" else "credential:news_feed",
                payload=payload,
            )

        by_helper = await card("by-helper", group, "connect_credential", helper.id)
        in_thread = await card("in-thread", conversation, "connect_credential", agent)
        about_account = await card("about-account", group, "create_agent", agent)
        elsewhere = await card("elsewhere", group, "connect_credential", other.id)
        await prepare_delete(session, owner, agent_id=helper.id)
        await prepare_delete(session, owner, thread_id=conversation.id)
        await prepare_delete(session, owner, account_id=account)
        assert (by_helper.status, by_helper.status_reason) == ("superseded", "agent_deleted")
        assert (in_thread.status, in_thread.status_reason) == ("superseded", "conversation_deleted")
        assert (about_account.status, about_account.status_reason) == (
            "superseded",
            "account_deleted",
        )
        assert elsewhere.status == "pending"
        # A card whose agent is gone still confirms: Lonora speaks the line instead (in
        # Arabic, the default when the conversation holds no owner message yet).
        elsewhere.agent_id = "deleted-agent"
        message = await ack(session, elsewhere)
        assert message.agent_id is None and message.content.startswith("تم الربط.")


@pytest.mark.asyncio
async def test_an_uncertain_trade_the_owner_is_already_asked_about_raises_no_second_alert(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread_id = task_db
    async with db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id)
        assert thread is not None
        run = RunRow(thread_id=thread_id, agent_id=agent, status="completed")
        session.add(run)
        await session.flush()
        for identifier in ("op-carded", "op-alerted", "op-silent"):
            session.add(
                TradingJournalRow(
                    operation_id=identifier,
                    owner_id=owner,
                    account_id="acc",
                    request_hash="h",
                    request={"symbol": "XAUUSD"},
                    status="ambiguous",
                    submitted_at=utcnow() - timedelta(hours=1),
                    result={"details": {"execution": {"agent_id": agent, "run_id": run.id}}},
                )
            )
        carded = await create_card(
            session,
            owner,
            card_id="resolve-carded",
            agent_id=agent,
            thread=thread,
            run_id=None,
            source="system",
            kind="resolve_operation",
            subject="operation:op-carded",
            payload={"operation_id": "op-carded"},
        )
        session.add(
            AttentionRow(
                owner_id=owner,
                agent_id=agent,
                thread_id=thread_id,
                logical_key="uncertain-op-alerted",
                coalesce_key="uncertain-op-alerted",
                importance="action_required",
                code="operation_uncertain",
                status="ready",
                parameters={"operation_id": "op-alerted"},
                due_at=utcnow(),
            )
        )
    watchdog = Watchdog(db, Liveness(), set())
    # Only the operation nobody has asked the owner about yet raises the aging alert.
    assert await watchdog.aging_operations() == 1
    async with db.sessions() as session, session.begin():
        row = await session.get(OwnerActionRow, carded.id, with_for_update=True)
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
    # Once its card expired unanswered, the aging alert is the owner's reminder.
    assert await watchdog.aging_operations() == 1
    async with db.sessions() as session:
        items = await session.scalars(
            select(AttentionRow.parameters).where(AttentionRow.code == "operation_unresolved")
        )
        assert sorted(item["operation_id"] for item in items) == ["op-carded", "op-silent"]
