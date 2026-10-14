from typing import Any, cast


async def canonical_broker_symbol(broker: Any, symbol: str) -> str:
    """Use the broker's own spelling when the request differs only by letter case."""
    try:
        names = await broker.symbols()
    except Exception:
        return symbol
    if not isinstance(names, list):
        return symbol
    catalog = [name for name in cast(list[object], names) if isinstance(name, str)]
    if symbol in catalog:
        return symbol
    folded = symbol.casefold()
    matches = [name for name in catalog if name.casefold() == folded]
    return matches[0] if len(matches) == 1 else symbol
