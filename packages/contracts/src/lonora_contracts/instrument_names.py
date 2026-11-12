"""The server's own names for instruments (docs/genui.md, Identity values).

Seeded from the reference's ``SYM_AR`` (Desktop-37 8007), with ``SYM_SHORT`` (8170) as the
accepted short forms. A broker spelling maps to its entry by the rule ``symbol_candidates``
uses (exact, then case-only, then a broker suffix: ``XAUUSD.r``, ``XAUUSDm``); a symbol with
no entry is named by its broker spelling, as the reference's ``symAr`` falls back (8008).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentName:
    symbol: str
    ar: str
    en: str
    short: str | None = None


INSTRUMENT_NAMES: tuple[InstrumentName, ...] = (
    InstrumentName("XAUUSD", "الذهب", "Gold", "ذهب"),
    InstrumentName("XAGUSD", "الفضة", "Silver", "فضة"),
    InstrumentName("EURUSD", "اليورو", "Euro", "يورو"),
    InstrumentName("GBPUSD", "الجنيه الإسترليني", "British pound", "جنيه"),
    InstrumentName("USDJPY", "الين", "Japanese yen", "ين"),
    InstrumentName("BTCUSD", "البيتكوين", "Bitcoin", "بيتكوين"),
    InstrumentName("USDCHF", "الفرنك السويسري", "Swiss franc"),
    InstrumentName("AUDUSD", "الدولار الأسترالي", "Australian dollar"),
    InstrumentName("US30", "مؤشر داو جونز", "Dow Jones index"),
)
_BY_SYMBOL = {item.symbol: item for item in INSTRUMENT_NAMES}
SUFFIX_SEPARATORS = frozenset(".-_#!+")
MAXIMUM_LOWERCASE_SUFFIX = 4


def instrument_entry(symbol: str) -> InstrumentName | None:
    """The table entry a broker spelling stands for, or None."""
    if not symbol:
        return None
    if symbol in _BY_SYMBOL:
        return _BY_SYMBOL[symbol]
    folded = symbol.casefold()
    for item in INSTRUMENT_NAMES:
        if item.symbol.casefold() == folded:
            return item
    for item in INSTRUMENT_NAMES:
        rest = symbol[len(item.symbol) :]
        if not rest or not folded.startswith(item.symbol.casefold()):
            continue
        if rest[0] in SUFFIX_SEPARATORS or (
            rest.isalpha() and rest.islower() and len(rest) <= MAXIMUM_LOWERCASE_SUFFIX
        ):
            return item
    return None


def instrument_name(symbol: str, language: str = "ar") -> str:
    """The server's name for a broker symbol in the owner's language."""
    entry = instrument_entry(symbol)
    if entry is None:
        return symbol
    return entry.en if language == "en" else entry.ar


def known_names(symbol: str) -> set[str]:
    """Every label the compiler accepts for an option of this symbol (before folding)."""
    names = {symbol}
    entry = instrument_entry(symbol)
    if entry is not None:
        names |= {entry.symbol, entry.ar, entry.en}
        if entry.short:
            names.add(entry.short)
    return names


def vocabulary_line() -> str:
    """The cached-prefix name table (§3.6): each symbol's English and Arabic names, the
    labels the compiler accepts (server matching data, not an example)."""
    return " · ".join(f"{item.symbol} {item.en} / {item.ar}" for item in INSTRUMENT_NAMES)
