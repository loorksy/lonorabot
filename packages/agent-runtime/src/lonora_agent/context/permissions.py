"""Small, server-derived authority context, refreshed with every model turn."""

import json

from lonora_db.agent_permissions import effective_permission
from lonora_db.owner_words import provisional_voice
from lonora_db.schema import RunRow
from lonora_tools.base import run_scope
from lonora_trading.agent_permission import acting_agent
from lonora_trading.authority_verdict import KINDS, RequestKind, authority_verdict, verdict_sentence
from sqlalchemy.ext.asyncio import AsyncSession


def permission_guidance(
    verdict: dict[RequestKind, str], *, mode: str, paused: bool, observe_only: bool
) -> str:
    """The mode, pause and run scope as data, then one sentence per kind of request."""
    facts = json.dumps({"trading_mode": mode, "paused": paused, "observe_only": observe_only})
    return (
        "[Lonora current financial permission]\n"
        "Server-derived and refreshed every turn; it supersedes older permission "
        "descriptions in conversation, plans and memory. It governs execution only: "
        "research, analysis, plans and monitoring stay open.\n"
        "<current_financial_permission>"
        + facts
        + "</current_financial_permission>\n"
        + "\n".join(verdict_sentence(kind, verdict[kind]) for kind in KINDS)
    )


async def permission_context(
    session: AsyncSession, owner_id: str, agent_id: str, run: RunRow | None = None
) -> str:
    # Observe-only wakes and helpers keep every non-financial ability.
    observe_only = run is not None and run_scope(run.trigger, run.model_metadata) != "full"
    provisional = (
        await provisional_voice(session, run) if run is not None and not observe_only else False
    )
    level = await effective_permission(session, owner_id, agent_id)
    agent = await acting_agent(session, owner_id, agent_id)
    verdict = authority_verdict(agent, level, provisional=provisional, observe_only=observe_only)
    return permission_guidance(
        verdict,
        mode="full" if agent.trading_mode == "full" else "ask",
        paused=agent.paused,
        observe_only=observe_only,
    )
