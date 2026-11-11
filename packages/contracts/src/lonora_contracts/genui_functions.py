"""The v2 card functions, values only (GENUI_PLAN §7.3), mirroring
``packages/core/src/genui/functions.ts``.

A bad argument returns None. The formatters (Fmt, Money, Pct, Signed, DayLabel, Plural)
return plain text without grouping or currency: the server only reads it for the privacy
guards, and display text is formatted on the client (§2.3). ``Random`` is client-only.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, cast

from .genui_expr import MAX_ITEMS, MAX_TEXT, is_number, loose_equal, normal, show, truthy

MAX_RANGE = MAX_ITEMS
MAX_LIST = 100


def _num(value: Any) -> float | None:
    if is_number(value) and math.isfinite(value):
        return float(value)
    return None


def _nums(values: tuple[Any, ...]) -> list[float] | None:
    flat: list[Any] = []
    for value in values:
        if isinstance(value, list):
            flat.extend(cast(list[Any], value))
        else:
            flat.append(value)
    numbers = [_num(item) for item in flat]
    if not numbers or any(item is None for item in numbers):
        return None
    return [cast(float, item) for item in numbers]


def _places(value: Any, default: int = 0) -> int | None:
    if value is None:
        return default
    number = _num(value)
    if number is None or not number.is_integer() or not 0 <= number <= 8:
        return None
    return int(number)


def _round(value: Any, places: Any = 0) -> Any:
    number, digits = _num(value), _places(places)
    if number is None or digits is None:
        return None
    precision = 10**digits
    # JavaScript Math.round(x * p) / p, half up toward +infinity.
    return normal(math.floor(number * precision + 0.5) / precision)


def _unary(function: Callable[[float], float]) -> Callable[[Any], Any]:
    def apply(value: Any) -> Any:
        number = _num(value)
        if number is None:
            return None
        try:
            return normal(function(number))
        except (ValueError, OverflowError):
            return None

    return apply


def _sqrt(value: Any) -> Any:
    number = _num(value)
    return None if number is None or number < 0 else normal(math.sqrt(number))


def _minmax(function: Callable[[list[float]], float]) -> Callable[..., Any]:
    def apply(*values: Any) -> Any:
        numbers = _nums(values)
        return None if numbers is None else normal(function(numbers))

    return apply


def _pow(base: Any, exponent: Any) -> Any:
    a, b = _num(base), _num(exponent)
    if a is None or b is None:
        return None
    try:
        return normal(math.pow(a, b))
    except (ValueError, OverflowError):
        return None


def _clamp(value: Any, low: Any, high: Any) -> Any:
    x, a, b = _num(value), _num(low), _num(high)
    if x is None or a is None or b is None or a > b:
        return None
    return normal(min(max(x, a), b))


def _fixed(value: Any, places: Any = 0) -> str | None:
    number, digits = _num(value), _places(places)
    if number is None or digits is None:
        return None
    rounded = _round(number, digits)
    return f"{cast(float, rounded):.{digits}f}"


def _pct(value: Any, places: Any = 0) -> Any:
    text = _fixed(value, places)
    return None if text is None else text + "%"


def _signed(value: Any, places: Any = 0) -> Any:
    number = _num(value)
    text = _fixed(abs(number) if number is not None else None, places)
    if text is None or number is None:
        return None
    return ("+" if number >= 0 else "−") + text


def _if(condition: Any, positive: Any = None, negative: Any = None) -> Any:
    return positive if truthy(condition) else negative


def _pick(key: Any, *pairs: Any) -> Any:
    for index in range(0, len(pairs) - 1, 2):
        if loose_equal(key, pairs[index]):
            return pairs[index + 1]
    return pairs[-1] if len(pairs) % 2 == 1 else None


def _len(value: Any) -> Any:
    if isinstance(value, list | str | dict):
        return len(cast(Any, value))
    return 0 if value is None else None


def _count(value: Any, target: Any = True) -> Any:
    if isinstance(value, dict):
        items = list(cast(dict[str, Any], value).values())
    elif isinstance(value, list):
        items = cast(list[Any], value)
    else:
        return 0 if value is None else None
    return sum(1 for item in items if loose_equal(item, target))


def _sum(value: Any) -> Any:
    if not isinstance(value, list):
        return None
    total = 0.0
    for item in cast(list[Any], value):
        number = _num(item)
        if number is not None:
            total += number  # plain left-to-right addition, as JavaScript's reduce
    return normal(total)


def _avg(value: Any) -> Any:
    if not isinstance(value, list) or not value:
        return None
    numbers = [_num(item) for item in cast(list[Any], value)]
    if any(item is None for item in numbers):
        return None
    total = 0.0
    for number in cast(list[float], numbers):
        total += number
    return normal(total / len(numbers))


def _range(start: Any, stop: Any, step: Any = 1) -> Any:
    a, b, s = _num(start), _num(stop), _num(step)
    if a is None or b is None or s is None or s == 0 or (b - a) / s < 0:
        return None
    count = math.floor((b - a) / s + 1e-9) + 1
    if count > MAX_RANGE:
        return None
    return [normal(a + index * s) for index in range(count)]


def _includes(values: Any, target: Any) -> Any:
    if not isinstance(values, list):
        return False
    return any(show(item) == show(target) for item in cast(list[Any], values))


def _join(values: Any, separator: Any = "، ") -> Any:
    if not isinstance(values, list) or not isinstance(separator, str):
        return None
    items = cast(list[Any], values)
    if len(items) > MAX_ITEMS:
        return None
    parts = ["" if item is None else show(item) for item in items]
    # Measured before it is built, so a nested Join never expands (review S1).
    if sum(map(len, parts)) + len(separator) * max(len(parts) - 1, 0) > MAX_TEXT:
        return None
    return separator.join(parts)


def ar_count(number: float) -> str:
    """Arabic plural category of a count: zero, one, two, few, many (reference arCount)."""
    n = abs(int(number))
    if n == 0:
        return "zero"
    if n == 1:
        return "one"
    if n == 2:
        return "two"
    rest = n % 100
    if 3 <= rest <= 10:
        return "few"
    return "many"


def _plural(
    count: Any, one: Any = "", two: Any = "", few: Any = "", many: Any = "", zero: Any = ""
):
    number = _num(count)
    if number is None:
        return None
    form = {"zero": zero, "one": one, "two": two, "few": few, "many": many}[ar_count(number)]
    if ar_count(number) == "zero" and not zero:
        form = many
    return show(form) if form is not None else ""


def _score(answers: Any, key: Any) -> Any:
    if not isinstance(answers, dict) or not isinstance(key, list):
        return None
    answers = cast(dict[str, Any], answers)
    return sum(
        1
        for index, expected in enumerate(cast(list[Any], key))
        if str(index) in answers and loose_equal(answers[str(index)], expected)
    )


def _day_label(value: Any) -> Any:
    return value if isinstance(value, str) and len(value) == 10 else None


def _default(value: Any, fallback: Any = None) -> Any:
    if value is None or value == "" or (is_number(value) and not math.isfinite(value)):
        return fallback
    return value


def _first(value: Any) -> Any:
    return cast(list[Any], value)[0] if isinstance(value, list) and value else None


def _last(value: Any) -> Any:
    return cast(list[Any], value)[-1] if isinstance(value, list) and value else None


def _take(values: Any, count: Any) -> Any:
    number = _num(count)
    if not isinstance(values, list) or number is None or not number.is_integer():
        return None
    items = cast(list[Any], values)
    n = int(number)
    return items[:n] if n >= 0 else items[n:]


def _filter(values: Any, key: Any, target: Any) -> Any:
    if not isinstance(values, list) or not isinstance(key, str):
        return None
    return [
        item
        for item in cast(list[Any], values)
        if isinstance(item, dict) and loose_equal(cast(dict[str, Any], item).get(key), target)
    ]


def _series(values: Any) -> list[float] | None:
    if not isinstance(values, list) or len(cast(list[Any], values)) > MAX_LIST:
        return None
    numbers = [_num(item) for item in cast(list[Any], values)]
    return None if any(item is None for item in numbers) else cast(list[float], numbers)


def _change(values: Any) -> Any:
    series = _series(values)
    if series is None:
        return None
    return [0, *[normal(b - a) for a, b in zip(series, series[1:], strict=False)]] if series else []


def _cumulative(values: Any) -> Any:
    series = _series(values)
    if series is None:
        return None
    total = 0.0
    result: list[Any] = []
    for item in series:
        total += item
        result.append(normal(total))
    return result


def _moving_avg(values: Any, window: Any) -> Any:
    series, size = _series(values), _num(window)
    if series is None or size is None or not size.is_integer() or size < 1:
        return None
    n = int(size)
    result: list[Any] = []
    for index in range(len(series)):
        part = series[max(0, index - n + 1) : index + 1]
        result.append(normal(sum(part) / len(part)))
    return result


def _allocate(total: Any, weights: Any) -> Any:
    """Split ``total`` by ``weights`` to the cent; the remainder cents go to the largest
    fractional parts first, so the shares always sum to the total."""
    amount, parts = _num(total), _series(weights)
    if amount is None or parts is None or not parts or any(p < 0 for p in parts):
        return None
    weight = sum(parts)
    if weight <= 0:
        return None
    cents = round(amount * 100)
    raw = [cents * part / weight for part in parts]
    floors = [math.floor(item) for item in raw]
    remainder = cents - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - floors[i]), i))
    for index in order[: max(0, remainder)]:
        floors[index] += 1
    return [normal(item / 100) for item in floors]


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "Round": _round,
    "Floor": _unary(math.floor),
    "Ceil": _unary(math.ceil),
    "Abs": _unary(abs),
    "Sqrt": _sqrt,
    "Min": _minmax(min),
    "Max": _minmax(max),
    "Pow": _pow,
    "Clamp": _clamp,
    "Fmt": _fixed,
    "Money": _fixed,
    "Pct": _pct,
    "Signed": _signed,
    "If": _if,
    "Pick": _pick,
    "Len": _len,
    "Count": _count,
    "Sum": _sum,
    "Range": _range,
    "Includes": _includes,
    "Join": _join,
    "Plural": _plural,
    "Score": _score,
    "DayLabel": _day_label,
    "Fact": lambda key=None: None,  # pyright: ignore[reportUnknownLambdaType]
    "Avg": _avg,
    "First": _first,
    "Last": _last,
    "Default": _default,
    "Change": _change,
    "Cumulative": _cumulative,
    "MovingAvg": _moving_avg,
    "Allocate": _allocate,
    "Take": _take,
    "Filter": _filter,
}
CLIENT_ONLY = frozenset({"Random"})
KNOWN = frozenset(FUNCTIONS) | CLIENT_ONLY
FORMATTERS = frozenset({"Fmt", "Money", "Pct", "Signed", "DayLabel", "Plural", "Join"})


def _arity(function: Callable[..., Any]) -> tuple[int, int | None]:
    import inspect

    parameters = list(inspect.signature(function).parameters.values())
    required = sum(
        1
        for p in parameters
        if p.kind is p.POSITIONAL_OR_KEYWORD and p.default is inspect.Parameter.empty
    )
    if any(p.kind is p.VAR_POSITIONAL for p in parameters):
        return required, None
    return required, len(parameters)


# How many arguments each function takes, ``functions.ts`` ARITY's twin (shared fixture):
# a call outside it fails the expression on both sides.
ARITY: dict[str, tuple[int, int | None]] = {name: _arity(f) for name, f in FUNCTIONS.items()}
