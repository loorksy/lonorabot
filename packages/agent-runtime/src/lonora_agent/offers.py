"""What a question's choice was bound to, and what a tapped choice leaves to do.

An offer is a ``wait_for_input`` question whose choices name the exact calls they stand
for. When the owner taps such a choice, those calls become an obligation of the Run the
tap resumes: the Run is told what the choice was bound to, and the end-of-turn check
(``conversation_gate``) counts the calls that followed. Only structure is read: tool
names and result fields, never what the owner or the model wrote.

Nothing here issues a call. A trade is never bound: an order is asked for with
``trade_execute``, whose own confirmation is the consent. Actions are bound only in a
Run that answers the owner's typed message and has read nothing others wrote, so text
from a page, a feed or another agent cannot put an action behind a label.
"""

import json
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_core.user_error import ToolRefusal
from lonora_db.runs import OFFER_OBLIGATION, require_lease
from lonora_tools.base import ToolScope
from lonora_tools.context import ToolContext
from lonora_tools.registry import BRIDGE_TOOLS, ToolRegistry
from lonora_tools.restrictions import owner_message_id
from lonora_tools.schema import ToolArgumentsError

from .runtime_notices import notice_message
from .uncertain_outcome import FINANCIAL_EFFECTS, INTERRUPTED

MAXIMUM_ARGUMENT_CHARS = 4000
# Calls that ask, wait or look up: none of them is something a choice can stand for.
UNBOUND = frozenset({"wait_for_input", "task_wait", "group_silence"}) | BRIDGE_TOOLS
NO_OWNER_WORDS = (
    "Actions can be bound to choices only in a turn that answers the owner's own typed "
    "message and has read nothing written by others (a page, a feed, a connected tool, "
    "another agent). Ask the same question without actions; when the owner answers, "
    "carry out the answer yourself."
)
NOT_A_TOOL = "it is not a tool of this turn; bind only tools you can call now"
MOVES_MONEY = (
    "it moves money, and a choice never stands for a trade; ask for an order or a close "
    "with trade_execute, whose own confirmation is the owner's consent"
)
NOT_AN_ACTION = "it asks, waits or looks up; it is not something a choice can stand for"
TOO_LONG = "its arguments are too long to bind"
NOT_ACCEPTED = "the tool would not accept these arguments as written"
# The kind of the notice that follows a pick: the check reads the transcript from it on.
PICKED = "choice_picked"
# Appended once to a reply that ends the turn with the picked choice left undone.
CHOICE_LINE_AR = "ما اخترته لم يُنفّذ بعد."
CHOICE_LINE_EN = "What you chose has not been carried out yet."

Exchange = tuple[ToolCall, dict[str, Any] | None]


def _invalid(choice: str, tool: str, why: str, **facts: Any) -> ToolRefusal:
    return ToolRefusal(
        "offer_action_invalid",
        400,
        details={
            "class": "input",
            "retryable": True,
            "hint": f"Choice {choice} binds {tool}, but {why}. Correct that action or "
            "remove it, then ask again.",
            **facts,
        },
    )


async def bind_choices(
    context: ToolContext, registry: ToolRegistry, scope: ToolScope, choices: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Check every bound action; return, per choice, what a tap does (for the card).

    Raises the refusal the model reads. A question whose choices bind nothing is not
    checked and returns nothing.
    """
    if not any(choice.get("actions") for choice in choices):
        return {}
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        answered = await owner_message_id(session, run)
        asked = cast(list[Any], run.execution_state.get("input_requests") or [])
    # A pick is a tap on a label the model wrote, not the owner's typed words: a Run it
    # resumed binds nothing more, whatever it had read before the question.
    picks = {
        cast(dict[str, Any], item).get("answer_message_id")
        for item in asked
        if isinstance(item, dict) and cast(dict[str, Any], item).get("selected_choice_id")
    }
    if answered is None or answered in picks:
        raise ToolRefusal(
            "offer_action_unavailable",
            409,
            details={"class": "input", "retryable": True, "hint": NO_OWNER_WORDS},
        )
    permitted = registry.names(scope)
    effects: dict[str, list[dict[str, Any]]] = {}
    for choice in choices:
        rows: dict[str, dict[str, Any]] = {}
        for action in cast(list[dict[str, Any]], choice.get("actions") or []):
            name, arguments = str(action["tool"]), cast(dict[str, Any], action["arguments"])
            tool = registry.tools.get(name)
            if tool is None or name not in permitted:
                raise _invalid(choice["id"], name, NOT_A_TOOL)
            if tool.financial or name in FINANCIAL_EFFECTS:
                raise _invalid(choice["id"], name, MOVES_MONEY)
            if name in UNBOUND:
                raise _invalid(choice["id"], name, NOT_AN_ACTION)
            if len(json.dumps(arguments, ensure_ascii=False)) > MAXIMUM_ARGUMENT_CHARS:
                raise _invalid(choice["id"], name, TOO_LONG)
            try:
                await registry.accepts(context, name, arguments)
            except (ToolArgumentsError, ToolRefusal) as error:
                # What the tool itself would answer: its issues are passed on, no values.
                issues = getattr(error, "issues", None)
                raise _invalid(
                    choice["id"], name, NOT_ACCEPTED, **({"issues": issues} if issues else {})
                ) from None
            row = rows.setdefault(
                name,
                {
                    "name": name,
                    "toolset": tool.toolset,
                    "effect": "read" if tool.read_only else "change",
                    "count": 0,
                },
            )
            row["count"] += 1
        if rows:
            effects[str(choice["id"])] = list(rows.values())
    return effects


def open_obligation(state: dict[str, Any]) -> dict[str, Any] | None:
    """The tapped choice this Run still answers, or ``None``."""
    raw = state.get(OFFER_OBLIGATION)
    if not isinstance(raw, dict):
        return None
    obligation = cast(dict[str, Any], raw)
    actions = obligation.get("actions")
    if obligation.get("status") != "open" or not isinstance(actions, list) or not actions:
        return None
    return obligation


def merge_answer(
    state: dict[str, Any], messages: list[ModelMessage], message_id: str, *, owner: bool
) -> None:
    """For each message a Run takes in, in order: the pick is followed by what it was
    bound to, and any later message of the owner's closes the offer unchecked."""
    obligation = open_obligation(state)
    if obligation is None:
        return
    if message_id == obligation.get("answer_message_id"):
        messages.append(notice_message(PICKED, choice_notice(obligation)))
    elif owner:
        state[OFFER_OBLIGATION] = {**obligation, "status": "superseded"}


def bound_tools(obligation: dict[str, Any]) -> dict[str, int]:
    """``{tool: how many calls of it the choice was bound to}``, in bound order."""
    counts: dict[str, int] = {}
    for action in cast(list[Any], obligation["actions"]):
        name = cast(dict[str, Any], action).get("tool") if isinstance(action, dict) else None
        if isinstance(name, str):
            counts[name] = counts.get(name, 0) + 1
    return counts


def outstanding(obligation: dict[str, Any], exchanges: list[Exchange]) -> dict[str, int]:
    """Bound calls with no settled call of their tool after the tap: ``{tool: missing}``.

    A call settles one bound call of its tool when it succeeded, or when its outcome is
    not known (it may have taken effect, so it is never asked for again). The arguments
    are not compared: a tool that succeeded with other values still acted on the choice,
    and asking again would repeat a change.
    """
    settled: dict[str, int] = {}
    for call, result in exchanges:
        if result is None or result.get("ok") is not False or result.get("code") == INTERRUPTED:
            settled[call.name] = settled.get(call.name, 0) + 1
    return {
        name: bound - settled.get(name, 0)
        for name, bound in bound_tools(obligation).items()
        if bound > settled.get(name, 0)
    }


def choice_notice(obligation: dict[str, Any]) -> str:
    """What the Run is told when the owner's tap resumes it: facts, not consent to more."""
    listed = "; ".join(
        f"{action['tool']} {json.dumps(action.get('arguments') or {}, ensure_ascii=False)}"
        for action in cast(list[dict[str, Any]], obligation["actions"])
    )
    return (
        f"The owner picked choice {obligation['choice_id']} of your question. When you "
        f"asked, you bound that choice to: {listed}. Carry out exactly that now and report "
        "the result. If something has changed since and it no longer applies, say plainly "
        "what was not done and why. The pick covers nothing beyond these calls."
    )
