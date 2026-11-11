"""The account's own symbol for an instrument request.

Reads resolve a common name or canonical code to the symbol the account really lists
(``read_symbol``). Anything that leads to an order, a grant or a restriction names a
symbol the catalogue lists exactly, letter case aside (``order_symbol``,
``canonical_broker_symbol``, ``restriction_symbol``): it is never rewritten to another
symbol. A request that is not listed fails with the account's real candidates and the
next call, so the model continues in the same run instead of asking the owner for a
broker's symbol name.
"""

import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, cast
from weakref import WeakKeyDictionary

from lonora_contracts.market import Instrument
from lonora_core.user_error import LonoraError, ToolRefusal
from lonora_market.instruments import catalogue_matches, confirms, contradicts, instrument_codes

MAXIMUM_CANDIDATES = 8
MAXIMUM_TEXT = 240
CATALOGUE_SECONDS = 300
USE_THE_SYMBOL = (
    "This account lists the instrument as {symbol}. Repeat the call with that exact "
    "symbol now; do not ask the owner for a symbol name."
)
CHECK_THE_SYMBOL = (
    "The account's only matching name is {symbol}; the broker's currencies do not "
    "confirm it. If its description is the instrument meant, repeat the call with that "
    "exact symbol; if not, say plainly that it is not offered. Do not ask the owner "
    "for a symbol name."
)
ASK_WHICH_CONTRACT = (
    "Several different contracts on this account match. Never choose one for an order, "
    "a grant or a restriction: ask the owner which, describing each choice in plain "
    "words (what one lot is, the smallest order), never as a question about symbol "
    "names; then repeat the call with the chosen exact symbol."
)
NOT_LISTED = (
    "No symbol on this account is confirmed for that instrument. The candidates marked "
    "similar are only its nearest names (market_instrument describes one) and "
    "market_symbols returns the catalogue; if the instrument is not offered, say so plainly."
)
SEVERAL_FOR_A_READ = (
    "Several contracts match on this account and this read used the first. Before any "
    "order ask the owner which contract, in plain words."
)


class SymbolNotResolved(ToolRefusal):
    """``symbol_not_found`` or ``symbol_ambiguous`` with what the model needs to go on."""

    def __init__(self, requested: str, candidates: list[str], names: list[object]):
        super().__init__("symbol_ambiguous" if len(candidates) > 1 else "symbol_not_found", 404)
        self.requested = requested
        self.candidates = candidates
        self.names = names
        self.details: dict[str, Any] = {
            # The unified error contract: a resolution failure the loop recovers from.
            "class": "resolution",
            "retryable": len(candidates) == 1,
            "hint": _hint(candidates),
            "requested_symbol": requested[:MAXIMUM_TEXT],
            "candidates": [{"symbol": name} for name in candidates[:MAXIMUM_CANDIDATES]],
            "next_actions": _next_actions(candidates),
        }
        if not candidates:
            # Not matches: the account's nearest names, marked so, for the model to judge.
            stem = instrument_codes(requested)[0][:3].casefold()
            self.details["candidates"] = [
                {"symbol": name, "similar": True}
                for name in names
                if isinstance(name, str) and len(stem) == 3 and stem in name.casefold()
            ][:MAXIMUM_CANDIDATES]


def _next_actions(candidates: list[str]) -> list[dict[str, Any]]:
    if not candidates:
        return [{"tool": "market_symbols"}]
    if len(candidates) > 1:
        return [{"ask_owner": "which_contract"}]
    return [{"repeat_with": {"symbol": candidates[0]}}]


def _hint(candidates: list[str]) -> str:
    if not candidates:
        return NOT_LISTED
    if len(candidates) > 1:
        return ASK_WHICH_CONTRACT
    return USE_THE_SYMBOL.format(symbol=candidates[0])


def catalog_symbol(names: list[object], symbol: str) -> str:
    """The catalog's spelling of ``symbol``: exact, or the single case-only match."""
    matches = catalogue_matches(names, symbol)
    if len(matches) == 1 and matches[0].casefold() == symbol.casefold():
        return matches[0]
    raise SymbolNotResolved(symbol, matches, names)


def _facts(name: str, instrument: Instrument | None) -> dict[str, Any]:
    """What tells one contract from another, for the model to put in plain words."""
    if instrument is None:
        return {"symbol": name}
    facts = instrument.model_dump(
        mode="json",
        include={
            "symbol",
            "description",
            "path",
            "contract_size",
            "base_currency",
            "profit_currency",
            "volume_min",
            "volume_step",
        },
    )
    return {
        key: value[:MAXIMUM_TEXT] if isinstance(value, str) else value
        for key, value in facts.items()
        if value not in (None, "")
    }


async def _verified(
    broker: Any, requested: str, names: list[str]
) -> list[tuple[str, Instrument | None]]:
    """The matches the broker's own specification does not contradict."""

    async def read(name: str) -> Instrument | None:
        try:
            return cast(Instrument, await broker.instrument(name))
        except Exception:
            return None

    selected = names[:MAXIMUM_CANDIDATES]
    code = instrument_codes(requested)[0]
    return [
        (name, instrument)
        for name, instrument in zip(
            selected, await asyncio.gather(*(read(name) for name in selected)), strict=True
        )
        if not isinstance(instrument, Instrument) or not contradicts(code, instrument)
    ]


async def _described(broker: Any, error: SymbolNotResolved) -> SymbolNotResolved:
    """The same failure with each candidate verified and described by the broker."""
    verified = await _verified(broker, error.requested, error.candidates)
    described = SymbolNotResolved(error.requested, [name for name, _ in verified], error.names)
    described.details["candidates"] = [_facts(name, instrument) for name, instrument in verified]
    if len(verified) == 1 and not confirms(instrument_codes(error.requested)[0], verified[0][1]):
        described.details["hint"] = CHECK_THE_SYMBOL.format(symbol=verified[0][0])
    return described


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
    except SymbolNotResolved as error:
        if require_exists:
            raise await _described(broker, error) from None
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
    try:
        return catalog_symbol(cast(list[object], names), symbol), True
    except SymbolNotResolved as error:
        raise await _described(broker, error) from None


async def order_symbol(broker: Any, symbol: str) -> str:
    """The symbol an order, a close or a sizing names, in the broker's spelling.

    A readable catalogue must list it exactly (letter case aside); it is never resolved
    to another symbol. An unreadable catalogue leaves it as given: the executor's own
    preflight still requires the broker's exact instrument, and an exit is not held back
    by a failed listing.
    """
    return (await restriction_symbol(broker, symbol))[0]


@dataclass
class _Catalogue:
    names: list[object]
    read_at: float
    resolved: dict[str, tuple[str, dict[str, Any]]] = field(
        default_factory=dict[str, tuple[str, dict[str, Any]]]
    )


# One catalogue per broker adapter, which is one per account connection version.
_CATALOGUES: WeakKeyDictionary[Any, _Catalogue] = WeakKeyDictionary()


async def _catalogue(broker: Any, *, refresh: bool = False) -> _Catalogue:
    try:
        cached = _CATALOGUES.get(broker)
    except TypeError:
        cached = None
    if cached and not refresh and monotonic() - cached.read_at < CATALOGUE_SECONDS:
        return cached
    names = await broker.symbols()
    if not isinstance(names, list):
        raise LonoraError("broker_symbols_unavailable", 409)
    catalogue = _Catalogue(cast(list[object], names), monotonic())
    try:
        _CATALOGUES[broker] = catalogue
    except TypeError:
        pass
    return catalogue


async def _resolved(broker: Any, requested: str) -> tuple[str, dict[str, Any]]:
    started = monotonic()
    catalogue = await _catalogue(broker)
    known = catalogue.resolved.get(requested)
    if known is not None:
        return known[0], {"symbol_resolution": dict(known[1]["symbol_resolution"])}
    matches = catalogue_matches(catalogue.names, requested)
    if not matches and catalogue.read_at < started:
        # A miss on a cached catalogue: the broker may have listed it since.
        catalogue = await _catalogue(broker, refresh=True)
        matches = catalogue_matches(catalogue.names, requested)
    if matches and all(name.casefold() == requested.casefold() for name in matches):
        if len(matches) == 1:
            return matches[0], {}
        raise await _described(broker, SymbolNotResolved(requested, matches, catalogue.names))
    verified = await _verified(broker, requested, matches)
    if not verified:
        raise SymbolNotResolved(requested, [], catalogue.names)
    symbol = verified[0][0]
    resolution: dict[str, Any] = {"requested": requested, "symbol": symbol}
    if verified[0][1] is not None and verified[0][1].description:
        # The broker's own words for it, so a wrong match is visible at once.
        resolution["description"] = verified[0][1].description[:MAXIMUM_TEXT]
    if len(verified) > 1:
        resolution["other_matches"] = [_facts(name, item) for name, item in verified[1:]]
        resolution["note"] = SEVERAL_FOR_A_READ
    catalogue.resolved[requested] = symbol, {"symbol_resolution": resolution}
    return symbol, {"symbol_resolution": dict(resolution)}


async def read_symbol(
    broker: Any, requested: str, *, require_exists: bool = False
) -> tuple[str, dict[str, Any]]:
    """The account's symbol for a read, and what to state in the result when the
    request named it another way (a common name, a code without the broker's affix).

    The catalogue is cached per account and read again on a miss. When it cannot be
    read, a lenient read keeps the request as given and the broker answers for it.
    """
    try:
        return await _resolved(broker, requested)
    except SymbolNotResolved as error:
        if not require_exists and not error.names:
            # An empty listing confirms nothing: the broker answers for the symbol.
            return requested, {}
        raise
    except Exception:
        if require_exists:
            raise
        return requested, {}
