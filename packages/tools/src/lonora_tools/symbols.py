from typing import Any, cast

from lonora_core.user_error import LonoraError


async def canonical_broker_symbol(broker: Any, symbol: str, *, require_exists: bool = False) -> str:
    """Use the broker's own spelling when the request differs only by letter case."""
    try:
        names = await broker.symbols()
    except Exception:
        if require_exists:
            raise
        return symbol
    if not isinstance(names, list):
        if require_exists:
            raise LonoraError("broker_symbols_unavailable", 409)
        return symbol
    catalog = [name for name in cast(list[object], names) if isinstance(name, str)]
    if symbol in catalog:
        return symbol
    folded = symbol.casefold()
    matches = [name for name in catalog if name.casefold() == folded]
    if len(matches) == 1:
        return matches[0]
    if require_exists:
        raise LonoraError("symbol_ambiguous" if matches else "symbol_not_found", 404)
    return symbol
