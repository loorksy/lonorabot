from typing import Any, cast

from lonora_core.user_error import LonoraError


def catalog_symbol(names: list[object], symbol: str) -> str:
    """The catalog's spelling of ``symbol``: exact, or the single case-only match."""
    catalog = [name for name in names if isinstance(name, str)]
    if symbol in catalog:
        return symbol
    folded = symbol.casefold()
    matches = [name for name in catalog if name.casefold() == folded]
    if len(matches) == 1:
        return matches[0]
    raise LonoraError("symbol_ambiguous" if matches else "symbol_not_found", 404)


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
    try:
        return catalog_symbol(cast(list[object], names), symbol)
    except LonoraError:
        if require_exists:
            raise
        return symbol


async def restriction_symbol(broker: Any | None, symbol: str) -> tuple[str, bool]:
    """A restriction symbol in the broker's spelling, and whether the catalog confirmed it.

    Enforcement matches the stored symbol exactly (ignoring case), so a symbol that a
    readable catalog does not list would never match a trade: that is an error the model
    or owner corrects (``symbol_not_found`` / ``symbol_ambiguous``). Only when the catalog
    cannot be read (no broker, a failed or empty listing) is the symbol kept as given and
    marked unverified, because recording an owner's narrowing must not depend on broker
    availability.
    """
    if broker is None:
        return symbol, False
    try:
        names = await broker.symbols()
    except Exception:
        return symbol, False
    if not isinstance(names, list) or not names:
        return symbol, False
    return catalog_symbol(cast(list[object], names), symbol), True
