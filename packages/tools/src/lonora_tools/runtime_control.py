from typing import Any

from lonora_contracts.domain import Board, Contract, Ticket
from lonora_core.run_state import is_conversational
from lonora_db.boards import BoardRepository
from lonora_db.runs import require_lease
from lonora_db.schema import ThreadRow
from lonora_db.tickets import TicketRepository
from lonora_db.transactions import resource_data
from lonora_trading.controls import read_controls
from pydantic import Field

from .base import Tool
from .context import ToolContext
from .memory import Empty


class WaitInput(Contract):
    question: str = Field(min_length=1, max_length=8000)


async def status(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.agent_state import agent_live_state

    async with context.db.sessions() as session:
        live = await agent_live_state(session, context.owner_id, context.agent_id)
    return {
        "run_id": context.lease.run_id,
        "trading": (await read_controls(context.db)).model_dump(),
        "agent_state": live.model_dump(mode="json"),
    }


async def wait(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"_runtime_wait": True, "question": args["question"]}


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
            "Read runtime and global financial controls; this tool cannot enable trading.",
            Empty,
            status,
            True,
        ),
        Tool(
            "wait_for_input",
            "Persist the run as waiting_input and ask the user a question before continuing.",
            WaitInput,
            wait,
        ),
        Tool(
            "group_silence",
            "Skip redundant background group participation only. Owner-selected requests, direct messages, and peer requests require a substantive answer or clarification.",
            Empty,
            silence,
            True,
        ),
    ]
