"""The lonora-ui v2 expression language, values only (GENUI_PLAN §2.2, §7.3).

The grammar is the reference's (Desktop-37 6287-6356): numbers without sign or exponent,
'…' or "…" strings without escapes, ``$state``, ``@Fn(...)``, locals and calc names,
``+ - * / %``, comparisons, ``&& || !``, ``?:``, ``.prop`` and ``[i]``. Semantics follow the
reference's JavaScript evaluator: ``+`` concatenates when either side is a string and
otherwise adds with null as 0, ``/`` and ``%`` by zero give 0, ``==`` is loose equality.

This module mirrors ``packages/core/src/genui/expr.ts`` for values; the shared vectors in
``tests/fixtures/genui/expr-vectors.json`` hold the two equal. It never formats display
text: the number formatters return plain number text, used only by the privacy guards.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

MAX_EXPRESSION_CHARS = 400
MAX_EXPRESSION_DEPTH = 12
MAX_PARSE_NESTING = 160
BLOCKED = frozenset({"__proto__", "prototype", "constructor"})
TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d+)?)|'(?P<sq>[^']*)'|\"(?P<dq>[^\"]*)\"|\$(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
    r"|@(?P<fn>[A-Za-z][A-Za-z0-9]*)|(?P<id>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>&&|\|\||==|!=|<=|>=|[-+*/%<>!?:().,\[\]]))"
)


class ExpressionError(ValueError):
    pass


Node = tuple[Any, ...]


def tokenize(source: str) -> list[tuple[str, Any]]:
    if len(source) > MAX_EXPRESSION_CHARS:
        raise ExpressionError("genui_expression_too_long")
    tokens: list[tuple[str, Any]] = []
    position = 0
    while position < len(source):
        if source[position:].strip() == "":
            break
        match = TOKEN.match(source, position)
        if match is None or match.end() == position:
            raise ExpressionError("genui_expression_invalid")
        position = match.end()
        kind = match.lastgroup
        assert kind is not None
        value = match.group(kind)
        if kind == "num":
            tokens.append(("num", float(value) if "." in value else int(value)))
        elif kind in {"sq", "dq"}:
            tokens.append(("str", value))
        else:
            tokens.append((kind, value))
    tokens.append(("end", None))
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, Any]]):
        self.tokens = tokens
        self.index = 0
        self.depth = 0

    def peek(self, value: str | None = None) -> bool:
        kind, token = self.tokens[self.index]
        return kind == "op" and token == value if value is not None else False

    def take(self, value: str) -> bool:
        if self.peek(value):
            self.index += 1
            return True
        return False

    def expect(self, value: str) -> None:
        if not self.take(value):
            raise ExpressionError("genui_expression_invalid")

    def enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_PARSE_NESTING:
            raise ExpressionError("genui_expression_too_deep")

    def leave(self) -> None:
        self.depth -= 1

    def parse(self) -> Node:
        node = self.ternary()
        if self.tokens[self.index][0] != "end":
            raise ExpressionError("genui_expression_invalid")
        return node

    def ternary(self) -> Node:
        self.enter()
        condition = self.binary(0)
        if self.take("?"):
            positive = self.ternary()
            self.expect(":")
            negative = self.ternary()
            condition = ("?", condition, positive, negative)
        self.leave()
        return condition

    LEVELS: tuple[tuple[str, ...], ...] = (
        ("||",),
        ("&&",),
        ("==", "!="),
        ("<", "<=", ">", ">="),
        ("+", "-"),
        ("*", "/", "%"),
    )

    def binary(self, level: int) -> Node:
        if level == len(self.LEVELS):
            return self.unary()
        self.enter()
        left = self.binary(level + 1)
        while True:
            kind, token = self.tokens[self.index]
            if kind == "op" and token in self.LEVELS[level]:
                self.index += 1
                left = ("b", token, left, self.binary(level + 1))
            else:
                break
        self.leave()
        return left

    def unary(self) -> Node:
        if self.take("!"):
            self.enter()
            node = ("u", "!", self.unary())
            self.leave()
            return node
        if self.take("-"):
            self.enter()
            node = ("u", "-", self.unary())
            self.leave()
            return node
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        while True:
            if self.take("."):
                kind, token = self.tokens[self.index]
                if kind != "id":
                    raise ExpressionError("genui_expression_invalid")
                self.index += 1
                node = ("g", node, ("c", token))
            elif self.take("["):
                self.enter()
                node = ("g", node, self.ternary())
                self.leave()
                self.expect("]")
            else:
                return node

    def primary(self) -> Node:
        kind, token = self.tokens[self.index]
        self.index += 1
        if kind in {"num", "str"}:
            return ("c", token)
        if kind == "var":
            return ("v", token)
        if kind == "fn":
            self.expect("(")
            args: list[Node] = []
            self.enter()
            if not self.take(")"):
                while True:
                    args.append(self.ternary())
                    if self.take(")"):
                        break
                    self.expect(",")
            self.leave()
            return ("f", token, tuple(args))
        if kind == "id":
            if token == "true":
                return ("c", True)
            if token == "false":
                return ("c", False)
            if token == "null":
                return ("c", None)
            return ("l", token)
        if kind == "op" and token == "(":
            self.enter()
            node = self.ternary()
            self.leave()
            self.expect(")")
            return node
        if kind == "op" and token == "[":
            items: list[Node] = []
            self.enter()
            if not self.take("]"):
                while True:
                    items.append(self.ternary())
                    if self.take("]"):
                        break
                    self.expect(",")
            self.leave()
            return ("a", tuple(items))
        raise ExpressionError("genui_expression_invalid")


_CACHE: dict[str, Node] = {}


def _depth(node: Node) -> int:
    """AST depth: a constant is 1; each operator, call, list or get adds one level."""
    children: list[Node] = []
    for item in node[1:]:
        if isinstance(item, tuple) and item and isinstance(item[0], str):
            children.append(cast(Node, item))
        elif isinstance(item, tuple):
            children.extend(cast(tuple[Node, ...], item))
    return 1 + max((_depth(child) for child in children), default=0)


def parse(source: str) -> Node:
    cached = _CACHE.get(source)
    if cached is not None:
        return cached
    node = _Parser(tokenize(source)).parse()
    if _depth(node) > MAX_EXPRESSION_DEPTH:
        raise ExpressionError("genui_expression_too_deep")
    if len(_CACHE) < 4096:
        _CACHE[source] = node
    return node


def references(source: str) -> tuple[set[str], set[str], set[str], set[str]]:
    """State keys, function names, local or calc names and fact keys an expression reads."""
    state: set[str] = set()
    functions: set[str] = set()
    names: set[str] = set()
    facts: set[str] = set()

    def walk(node: Node) -> None:
        tag = node[0]
        if tag == "v":
            state.add(node[1])
        elif tag == "l":
            names.add(node[1])
        elif tag == "f":
            functions.add(node[1])
            if node[1] == "Fact" and node[2] and node[2][0][0] == "c":
                facts.add(str(node[2][0][1]))
            for arg in node[2]:
                walk(arg)
        elif tag == "a":
            for item in node[1]:
                walk(item)
        else:
            for item in node[1:]:
                if isinstance(item, tuple):
                    walk(cast(Node, item))

    walk(parse(source))
    return state, functions, names, facts


# --- values -----------------------------------------------------------------


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def to_number(value: Any) -> float:
    """JavaScript ``Number(value)`` for the scalar kinds a card holds."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if is_number(value):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return 0.0
        if re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", text):
            return float(text)
        return math.nan
    return math.nan


def truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if is_number(value):
        return value != 0 and not math.isnan(value)
    if isinstance(value, str):
        return value != ""
    return True


def number_text(value: float | int) -> str:
    """JavaScript ``String(number)`` for finite values in the ranges cards use."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if float(value).is_integer() and abs(value) < 1e21:
        return str(int(value))
    return repr(float(value))


def show(value: Any) -> str:
    """Plain string conversion for ``+`` concatenation (``String(x)``)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if is_number(value):
        return number_text(value)
    if isinstance(value, list):
        return ",".join("" if item is None else show(item) for item in cast(list[Any], value))
    if isinstance(value, dict):
        return "[object Object]"
    return str(value)


def loose_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, list | dict) or isinstance(right, list | dict):
        return left is right
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    if isinstance(left, bool) and isinstance(right, bool):
        return left == right
    a, b = to_number(left), to_number(right)
    return not (math.isnan(a) or math.isnan(b)) and a == b


def normal(value: Any) -> Any:
    """Integers stay integers and finite floats stay floats; NaN and infinities are null."""
    if is_number(value):
        if not math.isfinite(value):
            return None
        if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
            return int(value)
    return value


def _compare(op: str, left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        a: Any = left
        b: Any = right
    else:
        a, b = to_number(left), to_number(right)
        if math.isnan(a) or math.isnan(b):
            return False
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def _binary(op: str, left: Any, right: Any) -> Any:
    if op == "+":
        if isinstance(left, str) or isinstance(right, str):
            return show(left) + show(right)
        return to_number(left or 0) + to_number(right or 0)
    if op in {"-", "*", "/", "%"}:
        a, b = to_number(left), to_number(right)
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if b == 0 or math.isnan(b):
            return 0
        if op == "/":
            return a / b
        return math.fmod(a, b)
    if op == "==":
        return loose_equal(left, right)
    if op == "!=":
        return not loose_equal(left, right)
    return _compare(op, left, right)


@dataclass
class Env:
    """The evaluation environment of one card: state values, calc results, locals, facts."""

    values: Mapping[str, Any]
    facts: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any]())
    names: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    functions: Mapping[str, Callable[..., Any]] | None = None


def _get(container: Any, key: Any) -> Any:
    if isinstance(key, str) and key in BLOCKED:
        raise ExpressionError("genui_expression_blocked")
    if isinstance(container, dict):
        container = cast(dict[str, Any], container)
        name = show(key) if not isinstance(key, str) else key
        return container.get(name)
    if isinstance(container, list | str):
        sequence = cast(list[Any] | str, container)
        if key == "length":
            return len(sequence)
        index = -1
        if is_number(key) and float(key).is_integer():
            index = int(key)
        elif isinstance(key, str) and key.isdigit():
            index = int(key)
        if 0 <= index < len(sequence):
            return sequence[index]
    return None


def evaluate_node(node: Node, env: Env) -> Any:
    tag = node[0]
    if tag == "c":
        return node[1]
    if tag == "v":
        name = node[1]
        if name in BLOCKED:
            raise ExpressionError("genui_expression_blocked")
        return env.values.get(name)
    if tag == "l":
        name = node[1]
        if name in BLOCKED:
            raise ExpressionError("genui_expression_blocked")
        return env.names.get(name)
    if tag == "a":
        return [evaluate_node(item, env) for item in node[1]]
    if tag == "u":
        value = evaluate_node(node[2], env)
        return not truthy(value) if node[1] == "!" else -to_number(value)
    if tag == "?":
        return evaluate_node(node[2] if truthy(evaluate_node(node[1], env)) else node[3], env)
    if tag == "g":
        return _get(evaluate_node(node[1], env), evaluate_node(node[2], env))
    if tag == "b":
        op = node[1]
        left = evaluate_node(node[2], env)
        if op == "&&":
            return evaluate_node(node[3], env) if truthy(left) else left
        if op == "||":
            return left if truthy(left) else evaluate_node(node[3], env)
        return _binary(op, left, evaluate_node(node[3], env))
    if tag == "f":
        from .genui_functions import FUNCTIONS

        functions = env.functions or FUNCTIONS
        function = functions.get(node[1])
        if function is None:
            raise ExpressionError("genui_function_unknown")
        if node[1] == "Fact":
            key = evaluate_node(node[2][0], env) if node[2] else None
            return env.facts.get(key) if isinstance(key, str) else None
        return function(*[evaluate_node(arg, env) for arg in node[2]])
    raise ExpressionError("genui_expression_invalid")


def evaluate(source: Any, env: Env, default: Any = None) -> Any:
    """``uxExpr``: non-strings are literals; a failure, undefined or non-finite is ``default``."""
    if not isinstance(source, str):
        return source
    try:
        value = normal(evaluate_node(parse(source), env))
    except (ExpressionError, RecursionError, OverflowError, ValueError, TypeError):
        return default
    return default if value is None and default is not None else value


TEMPLATE = re.compile(r"\{([^{}]*)\}")


def template_expressions(text: str) -> list[str]:
    return [match.group(1) for match in TEMPLATE.finditer(text)]


def render_template(text: str, env: Env) -> str:
    """Plain template text for the privacy guards (numbers unformatted)."""

    def replace(match: re.Match[str]) -> str:
        value = evaluate(match.group(1), env)
        if value is None:
            return ""
        if isinstance(value, list):
            return "، ".join(show(item) for item in cast(list[Any], value))
        return show(value)

    return TEMPLATE.sub(replace, text)


def environment(
    state: Mapping[str, Any],
    calc: Mapping[str, Any],
    facts: Mapping[str, Any],
    values: Mapping[str, Any] | None = None,
) -> Env:
    """``values`` over ``state``, then each calc in order into the same ``$`` namespace
    (later calcs see earlier ones), as the reference's env does (6379)."""
    current: dict[str, Any] = {**state, **(values or {})}
    env = Env(values=current, facts=facts)
    for name, source in calc.items():
        current[name] = evaluate(source, env)
    return env
