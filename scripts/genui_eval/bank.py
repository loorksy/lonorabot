"""The G0 fixture tool bank: every tool a decision-eval case calls is answered from data.

Report-only evaluation support (GENUI_PARITY_PLAN §10.6). The bank changes no product
behaviour: the runner keeps every Tool's definition, order, validation and guards and swaps
only handlers. No broker, network or model is reached from here.
"""

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.domain import Board, Ticket
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.market_watch import Watch
from lonora_contracts.position_sizing import PositionSizingResult
from lonora_core.user_error import LonoraError
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import BRIDGE_TOOLS, ToolRegistry
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/genui_decision"
BANK = FIXTURES / "tool_bank.json"
NOT_EXECUTED = "eval_tool_not_executed"
# Real handlers stay for bundled first-party instructions (a skill_view result is checked
# against its database receipt, so a fixture answer fails the Run) and for run control that
# reads only the disposable test database. Every other call is answered from the bank, and a
# tool the bank does not hold is recorded and answered with NOT_EXECUTED.
PASS_THROUGH = frozenset({"skills_list", "skill_view", "wait_for_input"})
# The real contract models inside each bank result, by JSON pointer ("*" = every item).
# A plain-dict result has no product model to check; its entry is empty on purpose.
CONTRACTS: dict[str, tuple[tuple[str, type[BaseModel]], ...]] = {
    "account_history": (),
    "account_read": (
        ("/account", AccountState),
        ("/positions/*", Position),
        ("/orders/*", Order),
    ),
    "agent_create": (),
    "agent_inspect": (),
    "board_list": (("/boards/*/payload", Board),),
    "economic_calendar_read": (),
    "list_accounts": (),
    "list_agents": (),
    "market_candles": (("/candles/*", Candle),),
    "market_instrument": (("", Instrument),),
    "market_position_size": (("", PositionSizingResult),),
    "market_quote": (("", Quote),),
    "market_sessions": (),
    "market_snapshot": (),
    "market_symbols": (),
    "memory_read": (),
    "memory_write": (),
    "model_list": (),
    "model_request": (),
    "news_feed_read": (),
    "owner_action_propose": (),
    "owner_notify": (),
    "routine_create": (),
    "routine_list": (),
    "ticket_create": (("/payload", Ticket),),
    "trade_close_positions": (),
    "trade_execute": (),
    "trade_record_history": (),
    "watch_cancel": (("/payload", Watch),),
    "watch_create": (("/payload", Watch),),
    "watch_list": (("/watches/*/payload", Watch),),
    "watch_pause": (("/payload", Watch),),
    "watch_update": (("/payload", Watch),),
    "web_fetch": (),
    "web_search": (),
}
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")


def load_bank(path: Path = BANK) -> dict[str, Any]:
    return json.loads(path.read_text())


def parts(value: Any, pointer: str) -> Iterator[Any]:
    """Every value a pointer with "*" segments addresses."""
    if not pointer:
        yield value
        return
    head, _, rest = pointer[1:].partition("/")
    tail = "/" + rest if rest else ""
    if head == "*":
        for item in cast(list[Any], value):
            yield from parts(item, tail)
    else:
        yield from parts(cast(dict[str, Any], value)[head], tail)


def entry_results(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every successful result an entry can answer with, a case context's answers included."""
    found = [entry["result"]] if "result" in entry else list(entry.get("results", {}).values())
    found.extend(entry.get("contexts", {}).values())
    return [cast(dict[str, Any], result) for result in found if "error" not in result]


def shift_times(value: Any, now: datetime, anchor: datetime) -> Any:
    """Move every timestamp by now - anchor, so the bank reads as observed just now."""
    if isinstance(value, dict):
        return {k: shift_times(v, now, anchor) for k, v in cast(dict[str, Any], value).items()}
    if isinstance(value, list):
        return [shift_times(item, now, anchor) for item in cast(list[Any], value)]
    if isinstance(value, str) and TIMESTAMP.fullmatch(value):
        moved = datetime.fromisoformat(value) + (now - anchor)
        text = moved.isoformat()
        return text.replace("+00:00", "Z") if value.endswith("Z") else text
    return value


def materialize(bank: Mapping[str, Any], ids: Mapping[str, str], now: datetime) -> dict[str, Any]:
    """Substitute this run's real identities and move the bank's times to now."""
    text = json.dumps(bank["tools"], ensure_ascii=False)
    for name, identity in ids.items():
        text = text.replace("{" + name + "}", identity)
    if re.search(r"\{[a-z_]+_id\}", text):
        raise ValueError("eval_bank_identity_missing")
    return shift_times(json.loads(text), now, datetime.fromisoformat(bank["anchor"]))


def for_context(tools: Mapping[str, Any], seed: str | None) -> dict[str, Any]:
    """The bank as one case sees it: an answer its context holds replaces the default.

    watch_list is empty unless the case's earlier turns created the gold watch (A01_sent).
    """
    return {
        name: {**entry, "result": entry["contexts"][seed]}
        if seed in entry.get("contexts", {})
        else entry
        for name, entry in tools.items()
    }


def answer(entry: Mapping[str, Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
    """The bank's answer to one validated call, exactly as the real handler would return it."""
    if "result" in entry:
        result = entry["result"]
    else:
        key = ":".join(str(arguments.get(name, "")).upper() for name in entry["by"])
        results = {k.upper(): v for k, v in entry["results"].items()}
        result = results.get(key, entry["otherwise"])
    if "error" in result:
        raise LonoraError(result["error"], 404)
    result = json.loads(json.dumps(result))
    if "echo" in entry:
        # Write tools store what they were given; echo it so the model reads its own values.
        target = result[entry["echo"]] if entry["echo"] else result
        target.update(json.loads(json.dumps(dict(arguments), default=str)))
    return result


def fixture_registry(tools: Mapping[str, Any], calls: list[dict[str, Any]]) -> ToolRegistry:
    """Today's registry with every handler answered from the bank and every call recorded."""
    real = load_tools()

    def handler(name: str):
        async def handle(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
            record: dict[str, Any] = {"tool": name, "call_id": context.call_id}
            record["arguments"] = json.loads(json.dumps(arguments, default=str))
            calls.append(record)
            if name not in tools:
                record["answered"] = NOT_EXECUTED
                raise LonoraError(NOT_EXECUTED, 501)
            record["answered"] = "bank"
            return answer(tools[name], arguments)

        return handle

    return ToolRegistry(
        [
            tool if name in PASS_THROUGH else replace(tool, handler=handler(name))
            for name, tool in real.tools.items()
            if name not in BRIDGE_TOOLS
        ]
    )
