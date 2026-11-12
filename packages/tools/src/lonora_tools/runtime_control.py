from typing import Any, Literal

from lonora_contracts.domain import Board, Contract, Ticket
from lonora_contracts.input_request import InputChoice
from lonora_core.public_reply import public_reply_violation
from lonora_core.run_state import is_conversational
from lonora_db.boards import BoardRepository
from lonora_db.runs import require_lease
from lonora_db.schema import ThreadRow, TradeApprovalRow
from lonora_db.tickets import TicketRepository
from lonora_db.transactions import resource_data
from pydantic import Field, model_validator
from sqlalchemy import select

from .base import Tool, eager_for
from .context import ToolContext
from .memory import Empty


class WaitInput(Contract):
    purpose: Literal["clarification", "execution_authorization"] = Field(
        default="clarification",
        description="Missing information only. Financial consent is trade_execute, never a question.",
    )
    question: str = Field(min_length=1, max_length=8000)
    choices: list[InputChoice] = Field(
        default_factory=list[InputChoice],
        max_length=6,
        description="Options for this question, in the conversation language; never a generic Approve/Reject list. Free text is always allowed.",
    )

    @model_validator(mode="after")
    def unique_choices(self) -> "WaitInput":
        if len({choice.id for choice in self.choices}) != len(self.choices):
            raise ValueError("input_choice_ids_must_be_unique")
        return self


async def status(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.agent_state import agent_live_state

    async with context.db.sessions() as session:
        live = await agent_live_state(session, context.owner_id, context.agent_id)
        run = await require_lease(session, context.lease)
        environment = run.execution_state.get("environment", {})
        operational = {
            "phase": environment.get("phase", "working"),
            "recent_observations": environment.get("recent", [])[-12:],
            "retry": environment.get("retry"),
            "task_id": run.model_metadata.get("task_id"),
            "trigger": run.trigger,
        }
    return {
        "run_id": context.lease.run_id,
        "agent_state": live.model_dump(mode="json"),
        "environment": operational,
    }


async def wait(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("purpose") == "execution_authorization":
        return {
            "ok": False,
            "code": "financial_consent_requires_trade_request",
            "next_tool": "trade_execute",
            # A trade is not the answer to an owner-only control (G0 baseline I07).
            "guidance": "An order or close is trade_execute. Lifting a "
            "pause, limits and authority are owner_action_propose cards (through tool_call); "
            "a pause the owner asks for is trade_restriction_create.",
        }
    if any(
        public_reply_violation(text)
        for text in [args["question"], *[choice["label"] for choice in args.get("choices", [])]]
    ):
        return {
            "ok": False,
            "code": "question_wording_private",
            "guidance": "Ask naturally in the owner's language without private identifiers, credentials or filesystem paths. Keep the actual question and relevant choices; do not ask for financial consent here.",
        }
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        pending = await session.scalar(
            select(TradeApprovalRow.id)
            .where(
                TradeApprovalRow.owner_id == context.owner_id,
                TradeApprovalRow.run_id == context.lease.run_id,
                TradeApprovalRow.status == "pending",
            )
            .limit(1)
        )
        if pending:
            return {
                "ok": False,
                "code": "trade_confirmation_already_pending",
                "approval_id": pending,
            }
    # A choice that binds nothing is stored as before: its id and label.
    choices = [
        {key: value for key, value in choice.items() if key != "actions" or value}
        for choice in args.get("choices", [])
    ]
    return {"_runtime_wait": True, "question": args["question"], "choices": choices}


async def silence(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        thread = await session.get(ThreadRow, context.thread_id)
        if thread is None or (not thread.group_id and is_conversational(run.trigger)):
            return {
                "ok": False,
                "code": "silence_requires_group",
                "guidance": "Respond to the request in this conversation.",
            }
        if is_conversational(run.trigger):
            return {
                "ok": False,
                "code": "reply_required",
                "guidance": "You were selected to answer this request. Give the substantive answer, or use wait_for_input for a necessary clarification. Do not stay silent.",
            }
    return {"_runtime_silence": True}


class TicketStart(Contract):
    ticket_id: str


async def boards(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        return {
            "boards": [
                resource_data(row)
                for row in await BoardRepository().list(session, context.owner_id)
            ]
        }


async def board_create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        existing = await session.get(BoardRepository.row_type, context.resource_id)
        row = existing or await BoardRepository().create(
            session,
            context.owner_id,
            args,
            agent_id=context.agent_id,
            resource_id=context.resource_id,
        )
        return resource_data(row)


async def ticket_create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        existing = await session.get(TicketRepository.row_type, context.resource_id)
        row = existing or await TicketRepository().create(
            session,
            context.owner_id,
            args,
            agent_id=context.agent_id,
            resource_id=context.resource_id,
        )
        return resource_data(row)


async def ticket_start(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.automation.background import start_ticket

    return await start_ticket(
        context.db,
        context.owner_id,
        args["ticket_id"],
        lease=context.lease,
        effect_key=context.effect_key,
    )


def tools() -> list[Tool]:
    return [
        Tool("board_list", "List durable task boards.", Empty, boards, True),
        Tool("board_create", "Create a durable board for tasks.", Board, board_create),
        Tool(
            "ticket_create", "Create a task ticket assigned to this agent.", Ticket, ticket_create
        ),
        Tool(
            "ticket_start",
            "Run an owned ticket through the same agent runtime.",
            TicketStart,
            ticket_start,
        ),
        Tool(
            "runtime_status",
            "Read this run's runtime state and your live agent state; this tool cannot enable trading.",
            Empty,
            status,
            True,
            poller=True,
        ),
        Tool(
            "wait_for_input",
            "Ask the owner one question when a decision that is really the owner's blocks progress; never a numbered or lettered menu. First recover earlier answers and finish the work already asked for. A choice that makes you act lists its exact calls in actions (never a trade): the pick is carried out as bound. With a trade's parameters known, call trade_execute instead of asking: an answer never approves a trade or grants authority, and nothing is asked while a trade confirmation is pending. Ask naturally, without naming tools, cards or internal processing.",
            WaitInput,
            wait,
            eager=eager_for("core"),
        ),
        Tool(
            "group_silence",
            "Skip redundant background group participation only. Owner-selected requests, direct messages, and peer requests require a substantive answer or clarification.",
            Empty,
            silence,
            True,
            parallel_safe=False,
        ),
    ]
