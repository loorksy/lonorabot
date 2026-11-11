"""Execute one tool call under the receipt, reconciliation and crash-replay rules."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_tools.base import ToolScope
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from lonora_tools.schema import ToolArgumentsError
from lonora_tools.symbols import SymbolNotResolved
from lonora_tools.tool_results import stored_result

from .environment import blocked_route, environment_state
from .skills.access import RunSkillAccess

log = logging.getLogger("lonora.tool_loop")


async def dispatch_call(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    call: ToolCall,
    scope: ToolScope,
    *,
    interrupted: bool,
    before_effect: Callable[[], Awaitable[None]] | None,
) -> dict[str, Any]:
    """Execute one call with the receipt, reconciliation and crash-replay rules.

    ``before_effect`` persists intent immediately before the handler can cross
    an effect boundary; a parallel read segment persists it once beforehand.
    """
    tool = registry.tools.get(call.name)
    blocked = blocked_route(state, call)
    environment = environment_state(state)
    result: dict[str, Any]
    try:
        receipt = await stored_result(context, call)
        if (
            receipt is not None
            and receipt.get("status") == "ambiguous"
            and tool
            and tool.financial
            and tool.replay_safe
        ):
            # The financial handler owns its durable journal and reconciles
            # the SAME operation. An observation receipt must not freeze it.
            receipt = None
        if receipt is not None:
            result = receipt
        elif (
            blocked
            and blocked.get("ambiguous")
            and blocked.get("receipt_replay")
            and tool
            and tool.financial
            and tool.replay_safe
        ):
            # Inspect/reconcile the SAME durable financial operation,
            # even if the model invents a new call ID. Never mint a new
            # approval/operation merely to learn the previous outcome.
            original = call.model_copy(update={"id": blocked["origin_call_id"]})
            result = await registry.execute(original, context, scope)
            # Not a new effect: the guardrails must not count it as a repeated send.
            result = {**result, "_runtime_reconciled": blocked["origin_call_id"]}
        elif blocked:
            result = {
                "ok": False,
                "code": "broker_result_ambiguous"
                if blocked.get("ambiguous")
                else "tool_route_exhausted",
                "recovery": {
                    "next_action": "reconcile_before_any_resend"
                    if blocked.get("ambiguous")
                    else "alternate_route_or_wait"
                },
            }
        elif interrupted and not (
            tool
            and (
                tool.read_only
                or (
                    tool.replay_safe
                    and (
                        call.id not in environment.get("legacy_pending", [])
                        or tool.legacy_replay_safe
                    )
                )
            )
        ):
            result = {"ok": False, "code": "tool_execution_uncertain"}
        else:
            if before_effect is not None:
                await before_effect()
            # The registry applies the per-tool dispatch deadline; financial
            # tools are never wrapped because they own broker deadlines.
            result = await registry.execute(
                call,
                replace(
                    context,
                    skill_access=RunSkillAccess(registry, tuple(state["instruction_skill_ids"])),
                ),
                scope,
            )
        result = {"ok": True, **result}
    except LonoraError as error:
        if error.code in {"stale_lease", "skill_continuation_unavailable"}:
            raise
        error_result: dict[str, Any] = {"ok": False, "code": error.code}
        if isinstance(error, ToolArgumentsError):
            error_result["issues"] = error.issues
            error_result["retryable"] = True
        if isinstance(error, SymbolNotResolved):
            # The account's real candidates and the next call: the model continues itself.
            error_result.update(error.details)
        result = error_result
    except (TimeoutError, ConnectionError) as error:
        result = {
            "ok": False,
            "code": (
                "tool_read_timeout"
                if isinstance(error, TimeoutError)
                else "tool_connection_failure"
            )
            if tool and tool.read_only
            else "tool_execution_uncertain",
        }
    except Exception as error:
        # Unknown tool failures remain observations. Exception content
        # may contain credentials; only the type belongs in diagnostics.
        log.warning("tool_execution_failed name=%s type=%s", call.name, type(error).__name__)
        result = {
            "ok": False,
            "code": "tool_internal_failure"
            if tool and tool.read_only
            else "tool_execution_uncertain",
        }
    return result
