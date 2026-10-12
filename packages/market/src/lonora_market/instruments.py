from lonora_contracts.market import Instrument
from lonora_core.user_error import LonoraError


def resolve_instrument(instruments: list[Instrument], symbol: str) -> Instrument:
    matches = [item for item in instruments if item.symbol == symbol]
    if len(matches) != 1:
        raise LonoraError("broker_symbol_not_found", 404)
    return matches[0]
