"""Bounded multilingual lexical matching; technical identifiers stay exact."""

import re
import unicodedata

MAX_QUERY_CHARS = 2000
MAX_QUERY_TERMS = 32
MAX_DOCUMENT_CHARS = 30000
CHUNK_CHARS = 2000
# Keep broker suffixes/prefixes as part of the raw token. Sentence punctuation
# is removed only for ordinary prose terms, never from a technical identifier.
TOKEN = re.compile(r"[#$]?\w+(?:[./:#-]\w+)*[./:#-]*", re.UNICODE)


def is_identifier(token: str) -> bool:
    # A contiguous uppercase run catches generic symbols with mixed-case
    # suffixes (XAUUSDm) without an instrument allowlist or treating Title Case
    # English words as case-sensitive symbols. A final period/colon on an
    # ordinary prose word remains sentence punctuation.
    body = token.rstrip(".:")
    return (
        any(c.isdigit() or c in "_./:#-$" for c in body)
        or re.search(r"[A-Z]{2,}", body) is not None
    )


def terms(text: str) -> set[str]:
    # Arabic vocalization is optional; do not stem or rewrite broker symbols.
    text = "".join(c for c in text if not ("\u064b" <= c <= "\u065f" or c == "\u0670"))
    return {
        (token if is_identifier(token) else token.rstrip(".:")).casefold()
        for token in TOKEN.findall(unicodedata.normalize("NFC", text))
    }


def query_terms(query: str) -> set[str]:
    return set(sorted(terms(query[:MAX_QUERY_CHARS]))[:MAX_QUERY_TERMS])


def identifiers(query: str) -> set[str]:
    return {token for token in TOKEN.findall(query[:MAX_QUERY_CHARS]) if is_identifier(token)}


def exact_identifiers_present(text: str, query: str) -> bool:
    return identifiers(query).issubset(set(TOKEN.findall(text)))


def lexical_score(text: str, query: str) -> float:
    wanted, present = query_terms(query), terms(text)
    if not wanted or not exact_identifiers_present(text, query):
        return 0.0
    return len(wanted & present) / len(wanted)


def document_chunks(document: str) -> list[tuple[int, str]]:
    """Offsets refer to the current durable document, never to a synthetic source."""
    document = document[:MAX_DOCUMENT_CHARS]
    boundaries = [0] + [m.start() for m in re.finditer(r"(?m)^#{1,3} ", document) if m.start()]
    boundaries.append(len(document))
    return [
        (offset, document[offset : min(offset + CHUNK_CHARS, end)])
        for start, end in zip(boundaries, boundaries[1:], strict=False)
        for offset in range(start, end, CHUNK_CHARS)
        if document[offset : min(offset + CHUNK_CHARS, end)].strip()
    ]


def retrieve_sections(document: str, query: str, limit: int = 6) -> list[str]:
    scored = [
        (lexical_score(text, query), offset, text) for offset, text in document_chunks(document)
    ]
    return [
        text
        for score, _, text in sorted(scored, key=lambda item: (-item[0], item[1]))[
            : max(0, min(limit, 8))
        ]
        if score > 0
    ]
