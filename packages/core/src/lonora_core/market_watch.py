from decimal import Decimal


def condition_met(
    condition: str, level: Decimal, current: Decimal, previous: Decimal | None
) -> bool:
    if condition == "above":
        return current > level
    if condition == "below":
        return current < level
    if condition == "cross_above":
        return previous is not None and previous <= level < current
    if condition == "cross_below":
        return previous is not None and previous >= level > current
    return False
