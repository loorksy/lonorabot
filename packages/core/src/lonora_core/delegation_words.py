"""Whether the owner's own words ask for full delegation (Arabic or English).

A grant card may open on Full delegation only when the owner's message asked for it; the
owner still chooses and signs with the passkey. This is a word check, not a reading of
intent: it looks for a delegation word ("تفويض", "صلاحيات", "تحكم", "delegate",
"control", "authority", ...) within two words of a fullness word ("كامل", "مطلق", "كل",
"full", "complete", "everything", ...). It misses nothing the owner can lose: a message
it does not recognize opens the card on Custom, and the owner can still pick Full there.
"""

import re
import unicodedata

# Arabic marks (harakat, tanween, shadda, sukun, Quranic marks) and tatweel; letter forms
# folded so "تفويضًا كاملًا", "تفويضا كاملا" and "التفويض الكامل" read alike.
_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})
_WORD = re.compile(r"[^\W_]+")
# Word stems that name handing over trading authority.
_DELEGATION_STEMS = (
    "فوض",  # فوّض، فوضه
    "فويض",  # تفويض، التفويض، تفويضا
    "صلاحي",  # صلاحية، صلاحيات، الصلاحيات
    "تحكم",
    "سيطر",
    "سلطه",
    "delegat",
    "control",
    "authorit",
    "autonom",
    "discretion",
    "permission",
    "power",
    "rein",
    "access",
)
# Stems, and whole words, that say "fully".
_FULL_STEMS = ("كامل", "كلي", "مطلق", "شامل")
_FULL_WORDS = frozenset(
    {
        "تام",
        "تاما",
        "التام",
        "تامه",
        "كل",
        "جميع",
        "full",
        "fully",
        "complete",
        "completely",
        "total",
        "totally",
        "entire",
        "entirely",
        "absolute",
        "unrestricted",
        "unlimited",
        "everything",
        "free",
    }
)
_WINDOW = 2


def _words(text: str) -> list[str]:
    folded = _MARKS.sub("", unicodedata.normalize("NFKC", text)).translate(_FOLD).casefold()
    return _WORD.findall(folded)


def _delegation(word: str) -> bool:
    return any(stem in word for stem in _DELEGATION_STEMS)


def _full(word: str) -> bool:
    return word in _FULL_WORDS or any(stem in word for stem in _FULL_STEMS)


def asks_full_delegation(text: str) -> bool:
    """Whether these words ask for full delegation: a delegation word and a fullness word
    at most two words apart ("تفويض كامل", "كل الصلاحيات", "full delegation", "delegate
    everything", "complete control"), or "carte blanche"."""
    words = _words(text)
    if any(a == "carte" and b == "blanche" for a, b in zip(words, words[1:], strict=False)):
        return True
    full = [index for index, word in enumerate(words) if _full(word)]
    return any(
        abs(index - other) <= _WINDOW
        for index, word in enumerate(words)
        if _delegation(word)
        for other in full
        if other != index
    )
