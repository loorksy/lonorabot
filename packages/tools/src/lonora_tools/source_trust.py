"""Trusting a source on the owner's own words (VISION 10.3.2): no card.

An agent adds a news feed's domain, a GitHub repository or owner, or an MCP server to the
owner's trusted list only when the owner's typed message this run answers names it
(``owner_message_id``: never a routine, peer or card wake, and never once the run has
read content someone else wrote). Otherwise the tool refuses with
``trust_requires_owner_message`` and nothing is trusted.

Naming is a strict, case-insensitive match of the identifier standing on its own: not
inside a longer domain, name or path. "evil-github.com", "news.github.com" and
"github.com.evil.io" do not name github.com; "acme/tools-fork", "acme/tools.js" and
"evil/acme/tools" do not name acme/tools; a URL names its host ("https://example.com/rss"
names example.com). A name the owner wrote as part of another saved name ("Notes" in
"Notes Pro") counts for the longer one only.

Writing (an MCP server's non-financial write tier) is asked for when the message that
names the server has a writing word ("write", "writing", "كتابة", "يكتب", ...) with no
negation ("no", "not", "don't", "never", "without", "لا", "بدون", ...) in the four words
before it. Anything else is the read tier.
"""

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from lonora_db.schema import MessageRow, RunRow, SteeringRow
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .restrictions import owner_message_id

CODE = "trust_requires_owner_message"
# Not after a word character, a dot, "@" or "-", nor right after "word/" (a longer path).
_BEFORE = r"(?<![\w.@-])(?<!\w/)"
# Not before a word character or "-", nor before a dot that continues the name.
_AFTER = r"(?![\w-]|\.[\w-])"
# The same, and not continued by a path either ("github.com/acme" alone, not ".../tools").
_AFTER_CLOSED = r"(?![\w-]|[./][\w-])"
_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_ARABIC = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})
_WORD = re.compile(r"[^\W_]+")
_WRITE_WORDS = frozenset(
    {
        "write",
        "writes",
        "writing",
        "كتابه",
        "الكتابه",
        "للكتابه",
        "بالكتابه",
        "والكتابه",
        "يكتب",
        "تكتب",
        "اكتب",
    }
)
# Words that take a writing word back when one of them is at most WINDOW words before
# it ("t" is the end of "don't", "can't", "won't" once split into words).
WINDOW = 4
_NEGATIONS = frozenset(
    {
        "no",
        "not",
        "never",
        "without",
        "nor",
        "dont",
        "t",
        "لا",
        "ولا",
        "بدون",
        "دون",
        "بلا",
        "ما",
        "مش",
        "غير",
        "ليس",
        "لن",
        "لم",
    }
)


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _pattern(name: str, closed: bool) -> re.Pattern[str]:
    return re.compile(_BEFORE + re.escape(name) + (_AFTER_CLOSED if closed else _AFTER))


def names_source(
    text: str, names: Iterable[str], *, closed: bool = False, others: Iterable[str] = ()
) -> bool:
    """Whether these words name the source by one of ``names`` (see the module rule).
    ``closed``: the name must not go on as a path. ``others``: other sources' names; one
    that contains a name of this source is taken out first, so it never counts."""
    wanted = {_fold(name) for name in names} - {""}
    said = _fold(text)
    for other in sorted({_fold(item) for item in others}, key=len, reverse=True):
        if other not in wanted and any(name in other for name in wanted):
            said = _pattern(other, False).sub(" ", said)
    return any(_pattern(name, closed).search(said) for name in wanted)


def asks_writes(text: str) -> bool:
    """Whether these words ask for writing: a writing word, not negated (module rule)."""
    folded = _MARKS.sub("", unicodedata.normalize("NFKC", text)).translate(_ARABIC).casefold()
    words = _WORD.findall(folded)
    return any(
        word in _WRITE_WORDS and _NEGATIONS.isdisjoint(words[max(0, index - WINDOW) : index])
        for index, word in enumerate(words)
    )


async def owner_named(
    session: AsyncSession,
    run: RunRow,
    names: Iterable[str],
    *,
    closed: bool = False,
    others: Iterable[str] = (),
) -> str | None:
    """The owner's own typed words this Run answers that name the source (the message it
    started on, or one he added while it worked), or None: no such message, it no longer
    stands for the owner (``owner_message_id``), or it does not name the source."""
    message_id = await owner_message_id(session, run)
    if message_id is None:
        return None
    added = select(SteeringRow.message_id).where(SteeringRow.run_id == run.id)
    said = await session.scalars(
        select(MessageRow.content).where(
            MessageRow.thread_id == run.thread_id,
            MessageRow.role == "user",
            # The owner's own words only: never a card's send or a follow-up tap.
            MessageRow.origin == "owner",
            or_(MessageRow.id == message_id, MessageRow.id.in_(added)),
        )
    )
    others = list(others)
    return next(
        (text for text in said if names_source(text, names, closed=closed, others=others)), None
    )


def refusal(**facts: Any) -> dict[str, Any]:
    """Nothing trusted: only the owner's own words in chat trust a source."""
    return {
        "ok": False,
        "code": CODE,
        "trusted": False,
        **facts,
        "recovery": "Nothing was trusted. Only the owner trusts a source: ask him to name it "
        "in chat (its domain, GitHub owner/repository or server name), then call this again "
        "before reading anything else in that run.",
    }
