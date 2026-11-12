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
"Notes Pro") counts for the longer one only. The same message must also ask to trust
that source, or give the server writing (below): a trust verb (trust, subscribe, add,
install, import, connect, allow, enable or use; ثق، اشترك، أضف، ثبّت، استورد، اربط، اسمح،
فعّل) at most TRUST_BEFORE words before the name or TRUST_AFTER words after it, with no
negation ("don't", "never", "no", "لا", "بدون", ...) in the NEGATION_REACH words before
the verb. A passing mention ("take notes on gold and add them to my journal", "what does
reuters.com say? use a chart") or a refusal ("don't trust reuters.com") trusts nothing.

Writing (an MCP server's non-financial write tier) is asked for only when the message
that names the server gives the server writing: "let/allow <server> write",
"<server> can write", "write access", "read and write", "writes are fine", «اسمح له
بالكتابة», «صلاحية الكتابة». The let-word's object and the modal's subject must be the
server: one of its names, or "it" / «له» / «لها» when the message names no other server.
A request for the agent or anyone else to write ("use Notes to write me a summary",
"let me write", "allow the agent to write", "Scout can write the report", «اكتب لي
ملخصا») is not one. A negation ("no", "not", "don't",
"never", "without", "لا", "بدون", ...) in the four words before, "nothing" or "none"
right after, or a read-only phrase anywhere ("read only", "reading only", «للقراءة
فقط») keeps the read tier. Anything else is the read tier.
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
# Words that give the server writing when one of them is at most four words before the
# writing word: "let it write", "allow Notes to write", «اسمح له بالكتابة».
_LET = frozenset(
    {"let", "lets", "allow", "allows", "allowing", "permit", "enable", "اسمح", "واسمح", "تسمح"}
)
# Let-words and modals that carry their own "it": «خلّه يكتب», «يمكنه الكتابة».
_LET_IT = frozenset({"خله", "خليه", "دعه", "اتركه", "يمكنه"})
# The server as the let-word's object or the modal's subject; a pronoun only when the
# message names no other server. Articles and «ل» may stand between ("the Wallet server").
_PRONOUNS = frozenset({"it", "له", "لها"})
_BETWEEN = frozenset({"the", "this", "that", "ل", "server"})
# "<server> can write"; «يستطيع الكتابة».
_MODALS = frozenset({"can", "may", "could", "should", "يستطيع", "يقدر", "تستطيع"})
# "write access", "writing permission"; and «صلاحية الكتابة», «إذن الكتابة» before it.
_GRANTS_AFTER = frozenset({"access", "permission", "permissions", "rights", "tier", "tools"})
_GRANTS_BEFORE = frozenset(
    {"صلاحيه", "صلاحيات", "اذن", "حق", "read", "قراءه", "القراءه", "للقراءه"}
)
_FINE = frozenset({"fine", "ok", "okay", "allowed", "welcome"})
_READ_ONLY = re.compile(r"\bread(?:ing)?[\s-]*only\b|\breadonly\b|قراءه فقط")
# Words that take a writing word back when one of them is at most WINDOW words before
# it ("t" is the end of "don't", "can't", "won't" once split into words), and the
# words after it that do ("write nothing").
WINDOW = 4
# A trust verb counts at most this many words before the source's name or after it, and
# not with a negation in the NEGATION_REACH words before it. URL schemes are not words.
TRUST_BEFORE = 5
TRUST_AFTER = 2
NEGATION_REACH = 3
_SCHEMES = frozenset({"http", "https"})
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
_NOTHING = frozenset({"nothing", "none", "شيء", "شي"})
# Asking for trust: these English words, or an Arabic verb (with و/ف before it and an
# object pronoun after it).
_TRUST = frozenset(
    {
        "trust",
        "trusted",
        "trusting",
        "subscribe",
        "subscribed",
        "add",
        "added",
        "adding",
        "install",
        "installed",
        "import",
        "imported",
        "connect",
        "connected",
        "allow",
        "allowed",
        "enable",
        "enabled",
        "use",
        "using",
    }
)
_TRUST_ARABIC = re.compile(
    "[وف]?(?:ثق|اثق|نثق|اشترك|اضف|ضيف|ثبت|استورد|اربط|اسمح|فعل)(?:ه|ها|هم|ي|وا|لي|نا)?"
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


def trusts_source(
    text: str, names: Iterable[str], *, closed: bool = False, others: Iterable[str] = ()
) -> bool:
    """Whether these words name the source and ask to trust it, or give it writing
    (module rule)."""
    names, others = list(names), list(others)
    return names_source(text, names, closed=closed, others=others) and (
        asks_trust(text, names) or asks_writes(text, names, others)
    )


def _words(text: str, names: Iterable[str] = ()) -> list[str]:
    """Folded words; each of ``names`` (the server's) reads as the one word "srv"."""
    folded = _MARKS.sub("", unicodedata.normalize("NFKC", text)).translate(_ARABIC).casefold()
    for name in sorted({_fold(item) for item in names} - {""}, key=len, reverse=True):
        folded = re.sub(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", " srv ", folded)
    return _WORD.findall(folded)


def asks_trust(text: str, names: Iterable[str]) -> bool:
    """Whether these words ask to trust the source (``names``): a trust verb near its
    name and not negated (module rule), not only a mention of it."""
    words = [word for word in _words(text, names) if word not in _SCHEMES]
    spots = [index for index, word in enumerate(words) if word == "srv"]
    for index, word in enumerate(words):
        if not (word in _TRUST or _TRUST_ARABIC.fullmatch(word)):
            continue
        if not _NEGATIONS.isdisjoint(words[max(0, index - NEGATION_REACH) : index]):
            continue
        if any(-TRUST_AFTER <= spot - index <= TRUST_BEFORE for spot in spots):
            return True
    return False


def asks_writes(text: str, names: Iterable[str] = (), others: Iterable[str] = ()) -> bool:
    """Whether these words give the server (``names``) writing (module rule); ``others``:
    the other servers' names, whose mention keeps "it" from meaning this server."""
    if _READ_ONLY.search(" ".join(_words(text))):
        return False
    names = list(names)
    words = _words(text, names)
    alone = not any(names_source(text, [other], others=names) for other in others)
    subjects = {"srv", *(_PRONOUNS if alone else ())}

    def server_at(index: int, step: int) -> bool:
        """Whether the server stands at ``index``, skipping articles in ``step``."""
        while 0 <= index < len(words) and words[index] in _BETWEEN:
            index += step
        return 0 <= index < len(words) and words[index] in subjects

    def gives(index: int) -> int | None:
        """Where the words that give the server writing start, or None."""
        start = max(0, index - 4)
        for offset, word in enumerate(words[start:index]):
            if word in _LET_IT or (word in _LET and server_at(start + offset + 1, 1)):
                return start + offset
        previous = words[index - 1] if index else ""
        following = words[index + 1 : index + 3]
        if previous in _MODALS and server_at(index - 2, -1):
            return index - 1
        if previous in _GRANTS_BEFORE:
            return index - 1
        if previous == "and" and index > 1 and words[index - 2] in _GRANTS_BEFORE:
            return index - 2  # "read and write"
        if following[:1] and following[0] in _GRANTS_AFTER:
            return index
        if len(following) == 2 and following[0] in {"is", "are"} and following[1] in _FINE:
            return index
        return None

    for index, word in enumerate(words):
        if word not in _WRITE_WORDS or (start := gives(index)) is None:
            continue
        if not _NEGATIONS.isdisjoint(words[max(0, start - WINDOW) : index]):
            continue
        if not _NOTHING.isdisjoint(words[index + 1 : index + 3]):
            continue
        return True
    return False


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
    stands for the owner (``owner_message_id``), or it does not name the source and ask
    for trust."""
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
        (text for text in said if trusts_source(text, names, closed=closed, others=others)),
        None,
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
