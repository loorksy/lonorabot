"""Small, deterministic visual compatibility helpers; never execute model code."""

import math
import re
from decimal import Decimal
from typing import Any, cast

KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")
MARKER = re.compile(r"\{\{([^{}]+)\}\}")
RESERVED = {"__proto__", "prototype", "constructor"}
EXTENDED_ARITY = {
    "floor": (1, 1),
    "ceil": (1, 1),
    "sqrt": (1, 1),
    "pow": (2, 2),
    "clamp": (3, 3),
    "percent": (2, 2),
    "change": (2, 2),
    "concat": (1, 8),
}


def has_visual_placeholder(value: str) -> bool:
    return "{{" in value


def legacy_visual_bindings(value: Any) -> Any:
    """Adapt only old text/badge bindings to declared scalar state, without mutation.

    This is not string evaluation or guessed market data. Other display fields,
    missing state and malformed markers remain invalid for the normal contract.
    """
    if not isinstance(value, dict):
        return value
    source = cast(dict[str, Any], value)
    state_value = source.get("state", {})
    if not isinstance(state_value, dict):
        return source
    state = cast(dict[str, Any], state_value)

    def concat(parts: list[Any]) -> Any:
        while len(parts) > 8:
            parts = [{"op": "concat", "args": parts[i : i + 8]} for i in range(0, len(parts), 8)]
        return {"op": "concat", "args": parts}

    def walk(node: Any, depth: int = 0) -> Any:
        if not isinstance(node, dict):
            return node
        original = cast(dict[str, Any], node)
        if depth > 10:
            return original
        result = dict(original)
        text = original.get("text")
        if (
            original.get("type") in {"text", "badge"}
            and "value" not in original
            and isinstance(text, str)
            and len(text) <= 4000
            and has_visual_placeholder(text)
        ):
            parts: list[Any] = []
            position = 0
            valid = True
            for match in MARKER.finditer(text):
                key = match[1]
                if not KEY.fullmatch(key) or key in RESERVED or key not in state:
                    valid = False
                    break
                if match.start() > position:
                    parts.append(text[position : match.start()])
                parts.append({"state": key})
                position = match.end()
            if position < len(text):
                parts.append(text[position:])
            if (
                valid
                and parts
                and all(
                    not isinstance(part, str) or not has_visual_placeholder(part) for part in parts
                )
            ):
                result.pop("text")
                result["value"] = concat(parts)
        children = original.get("children")
        if isinstance(children, list):
            result["children"] = [walk(child, depth + 1) for child in cast(list[Any], children)]
        return result

    return {**source, "root": walk(source.get("root"))}


def evaluate_extended_visual_op(op: str, args: list[Any]) -> Any:
    """Same finite scalar semantics as the shared Web/native evaluator."""
    if op not in EXTENDED_ARITY:
        return None
    minimum, maximum = EXTENDED_ARITY[op]
    if not minimum <= len(args) <= maximum:
        return None
    if op == "concat":
        if any(arg is None or not isinstance(arg, str | int | float | bool) for arg in args):
            return None
        if any(
            isinstance(arg, int | float) and not isinstance(arg, bool) and not _finite(arg)
            for arg in args
        ):
            return None

        def scalar_text(arg: Any) -> str:
            if isinstance(arg, bool):
                return "true" if arg else "false"
            if isinstance(arg, int | float):
                if arg == 0:
                    return "0"
                # Match JavaScript's scalar spelling at the renderer boundary:
                # fixed notation in [1e-6, 1e21), otherwise normalized exponent.
                if 1e-6 <= abs(arg) < 1e21:
                    fixed = format(Decimal(str(arg)), "f")
                    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
                mantissa, exponent = repr(float(arg)).lower().split("e")
                return (
                    f"{mantissa.removesuffix('.0')}e{int(exponent):+d}"
                    if int(exponent) >= 0
                    else f"{mantissa.removesuffix('.0')}e{int(exponent)}"
                )
            return str(arg)

        result = "".join(scalar_text(arg) for arg in args)
        return result if len(result) <= 4000 else None
    if any(
        isinstance(arg, bool) or not isinstance(arg, int | float) or not _finite(arg)
        for arg in args
    ):
        return None
    try:
        if op == "floor":
            result = math.floor(args[0])
        elif op == "ceil":
            result = math.ceil(args[0])
        elif op == "sqrt":
            result = math.sqrt(args[0])
        elif op == "pow":
            result = math.pow(args[0], args[1])
        elif op == "clamp":
            result = min(args[2], max(args[1], args[0])) if args[1] <= args[2] else None
        elif op == "percent":
            result = args[0] / args[1] * 100 if args[1] else None
        else:
            result = (args[0] - args[1]) / abs(args[1]) * 100 if args[1] else None
        return result if result is not None and math.isfinite(result) else None
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def _finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
