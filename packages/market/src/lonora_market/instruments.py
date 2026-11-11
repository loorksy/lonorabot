"""Which symbols of one broker account an instrument request names.

Deterministic and derived from the account's own catalogue: a request is a broker
symbol, a canonical code ("XAUUSD") or a common name («الذهب», "gold"), and a catalogue
name matches when it is that code wrapped in a broker affix ("XAUUSDm", "XAUUSD.pro",
"#XAUUSD"). No per-broker list exists. Choosing among several matches, and whether a
match may be used at all, belongs to the caller: reads may pick, orders never do.
"""

from lonora_contracts.instrument_names import (
    INSTRUMENT_NAMES,
    MAXIMUM_LOWERCASE_SUFFIX,
    SUFFIX_SEPARATORS,
    InstrumentName,
)
from lonora_contracts.market import Instrument
from lonora_core.user_error import LonoraError

MINIMUM_CODE = 3


def resolve_instrument(instruments: list[Instrument], symbol: str) -> Instrument:
    matches = [item for item in instruments if item.symbol == symbol]
    if len(matches) != 1:
        raise LonoraError("broker_symbol_not_found", 404)
    return matches[0]


def _folded(name: str) -> str:
    return "".join(name.casefold().split()).replace("/", "").removeprefix("ال")


_BY_NAME: dict[str, InstrumentName] = {
    _folded(name): item
    for item in INSTRUMENT_NAMES
    for name in (item.symbol, item.ar, item.en, item.short)
    if name
}


def instrument_codes(requested: str) -> list[str]:
    """The codes a request stands for, the canonical one first: a known instrument's
    code and its English word (some brokers list gold as "GOLD"), else the request."""
    entry = _BY_NAME.get(_folded(requested))
    if entry is not None:
        return [entry.symbol, entry.en]
    return ["".join(requested.split()).replace("/", "")]


def _wraps(name: str, code: str) -> bool:
    """Whether ``name`` is ``code`` alone or inside a broker affix: a separator next to
    the code ("XAUUSD.pro", "XAUUSD_i", "#XAUUSD", "m.XAUUSD"), or a short lowercase
    suffix ("XAUUSDm"). Letters or digits that extend the code ("XAUUSDT", "US300") name
    another instrument, and a fragment ("pro", "m") is never a code."""
    start = name.casefold().find(code.casefold())
    if len(code) < MINIMUM_CODE or start < 0:
        return False
    prefix, suffix = name[:start], name[start + len(code) :]
    return (not prefix or (prefix[-1] in SUFFIX_SEPARATORS and _short(prefix[:-1]))) and (
        not suffix
        # A separated suffix longer than the code is the name, and the "code" its affix.
        or (suffix[0] in SUFFIX_SEPARATORS and sum(map(str.isalnum, suffix)) <= len(code))
        or (suffix.isalpha() and _short(suffix))
    )


def _short(letters: str) -> bool:
    return not letters or (
        letters.isalpha() and letters.islower() and len(letters) <= MAXIMUM_LOWERCASE_SUFFIX
    )


def catalogue_matches(names: list[object], requested: str) -> list[str]:
    """The catalogue's names for ``requested``: the exact name, else the names that
    differ only by letter case, else every name that wraps its code (or, when none
    does, its English word), the shortest first."""
    catalogue = [name for name in names if isinstance(name, str)]
    if requested in catalogue:
        return [requested]
    folded = requested.casefold()
    same = [name for name in catalogue if name.casefold() == folded]
    if same:
        return same
    for code in instrument_codes(requested):
        matches = [name for name in catalogue if _wraps(name, code)]
        if matches:
            return sorted(matches, key=lambda name: (len(name), name))
    return []


def _pair(instrument: Instrument | None) -> str | None:
    """The currency pair the broker reports, when it reports one. The same currency on
    both sides (a CFD quoted and margined in dollars) says nothing about the underlying."""
    if instrument is None or not instrument.base_currency or not instrument.profit_currency:
        return None
    base, quote = instrument.base_currency.strip(), instrument.profit_currency.strip()
    return None if base.casefold() == quote.casefold() else (base + quote).casefold()


def contradicts(code: str, instrument: Instrument) -> bool:
    """Whether the broker's own base and quote currency show that ``instrument`` is not
    the currency pair ``code``. Unreported currencies and non-pair codes prove nothing."""
    pair = _pair(instrument)
    return len(code) == 6 and code.isalpha() and pair is not None and pair != code.casefold()


def confirms(code: str, instrument: Instrument | None) -> bool:
    """Whether the broker's own base and quote currency are the pair ``code`` names."""
    return _pair(instrument) == code.casefold()
