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
    if condition == "changed":
        return previous is not None and previous != current
    if condition == "closed":
        return previous is not None and previous > 0 and current == 0
    if condition == "opened":
        return previous == 0 and current > 0
    if condition == "due":
        return current > 0
    return False
