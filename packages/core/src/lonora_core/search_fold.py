"""Arabic folding for the owner's search, identical in Python and in SQL.

A query and the searched text are both folded: lower-cased, the alef variants
(أ إ آ ٱ) become ا, ى becomes ي, ة becomes ه, and tashkeel and tatweel are removed. The
SQL side is ``translate(lower(x), FOLD_FROM, FOLD_TO)``: characters of ``FOLD_FROM``
beyond the length of ``FOLD_TO`` are deleted. Migration ``0045_chat_lists`` indexes that
exact expression on ``ln_messages.content`` (pg_trgm), so the constants are rendered
inline in queries (``literal_execute``) for the planner to match the index.
"""

from sqlalchemy import Text, bindparam, func
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

SearchColumn = ColumnElement[str] | InstrumentedAttribute[str]

ALEF_VARIANTS = "أإآٱ"
TASHKEEL = "ًٌٍَُِّْٰ"
TATWEEL = "ـ"
FOLD_FROM = ALEF_VARIANTS + "ىة" + TASHKEEL + TATWEEL
FOLD_TO = "ا" * len(ALEF_VARIANTS) + "يه"
_TABLE = {
    ord(source): FOLD_TO[index] if index < len(FOLD_TO) else None
    for index, source in enumerate(FOLD_FROM)
}


def fold(text: str) -> str:
    """The folded form of a query or a text; whitespace runs collapse to one space."""
    return " ".join(text.lower().translate(_TABLE).split())


def folded(column: SearchColumn) -> ColumnElement[str]:
    """The SQL expression the search compares and the index covers."""
    return func.translate(
        func.lower(column),
        bindparam("fold_from", FOLD_FROM, type_=Text, literal_execute=True),
        bindparam("fold_to", FOLD_TO, type_=Text, literal_execute=True),
    )


def folded_sql(column: str) -> str:
    """The same expression as DDL text, for the migration's index."""
    return f"translate(lower({column}), '{FOLD_FROM}', '{FOLD_TO}')"
