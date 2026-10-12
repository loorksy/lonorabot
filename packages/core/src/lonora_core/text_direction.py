import unicodedata


def direction(text: str) -> str:
    for char in text:
        bidi = unicodedata.bidirectional(char)
        if bidi in {"R", "AL"}:
            return "rtl"
        if bidi == "L":
            return "ltr"
    return "auto"


def isolate(value: str) -> str:
    return "\u2068" + value + "\u2069"
