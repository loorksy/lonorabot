"""What the execution door does now with each kind of financial request (read-only).

The permission frame and the voice leg tell the agent this verdict; the door
(``agent_permission.require_operation_permission`` and the trade tools) still decides
every request. It reads the inputs the door reads: the permission level, the agent's
row (mode, pause, role, standing instruction), provisional speech and the run's scope.
Until grants are deleted (14.2), an active grant's path is mirrored too.
"""

from typing import Literal

from lonora_contracts.agent_permissions import PermissionLevel
from lonora_db.schema import AgentRow

RequestKind = Literal["new_risk", "reduce_risk", "others_ticket"]
KINDS: tuple[RequestKind, ...] = ("new_risk", "reduce_risk", "others_ticket")

SUBJECT: dict[RequestKind, str] = {
    "new_risk": "A request that adds risk",
    "reduce_risk": "A request that reduces risk on your own ticket",
    "others_ticket": "A request on a ticket your own order did not open",
}
SENTENCE: dict[tuple[RequestKind, str], str] = {
    ("new_risk", "execute"): "A request that adds risk executes without a card.",
    ("new_risk", "needs_approval"): "A request that adds risk needs the owner's approval: it "
    "waits on its Trade Approval card, and only the owner's tap on Approve sends it.",
    ("new_risk", "grant_or_approval"): "A request that adds risk executes when an active "
    "grant covers it exactly; otherwise it waits on its Trade Approval card for the owner's "
    "tap.",
    ("reduce_risk", "execute"): "A request that reduces risk on your own ticket (a full or "
    "partial close, cancelling an order that would add exposure, a new stop or one moved "
    "toward the market) executes without a card.",
    ("others_ticket", "execute"): "A ticket your own order did not open is yours to manage "
    "too: the owner told you to manage all positions.",
    ("others_ticket", "lead"): "As Lonora you act on any agent's ticket; new risk on a "
    "ticket of an agent in Ask still needs the owner's approval.",
    ("others_ticket", "refused:ticket_not_owned"): "A request on a ticket your own order "
    "did not open is refused (ticket_not_owned), unless the owner asks for it in the typed "
    "message this run answers and nothing others wrote, an attachment included, has "
    "reached this run.",
}


def authority_verdict(
    agent: AgentRow, level: PermissionLevel, *, provisional: bool, observe_only: bool
) -> dict[RequestKind, str]:
    """Per kind: ``execute``, ``needs_approval``, ``grant_or_approval``, ``lead`` or
    ``refused:<the door's code>``."""
    refused = (
        "observe_only_execution_forbidden"
        if observe_only
        else "agent_analysis_only"
        if level == "analysis"
        else None
    )
    if refused:
        return dict.fromkeys(KINDS, "refused:" + refused)
    new_risk = (
        "refused:agent_paused"
        if agent.paused
        else "execute"
        if agent.trading_mode == "full"
        # A grant is never spent by provisional speech (owner_words.provisional_voice).
        else "grant_or_approval"
        if level == "autonomous" and not provisional
        else "needs_approval"
    )
    others = (
        "lead"
        if agent.role == "personal"
        else "execute"
        if agent.manages_all_positions
        else "refused:ticket_not_owned"
    )
    return {"new_risk": new_risk, "reduce_risk": "execute", "others_ticket": others}


def verdict_sentence(kind: RequestKind, verdict: str) -> str:
    """The one sentence the agent reads for ``kind``."""
    if (kind, verdict) in SENTENCE:
        return SENTENCE[(kind, verdict)]
    return f"{SUBJECT[kind]} is refused ({verdict.removeprefix('refused:')})."
