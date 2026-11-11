"""What the owner called a thing, turned into the thing itself.

An account, an agent, a watch, a routine or a task reaches a tool as the id the model
read, or as the words the owner used for it. The tool's own list is the only source of
candidates, so nothing outside the caller's reach is ever offered. The answer is one of
four: the id itself, one item that fits, several, none.

A read may use the one item that fits, and a stop of the agent's own item may use one
whose name is exactly that; both say so in their result. Anything else is refused with
the item, so the next call names it by its id: a change is never pointed at something
the caller did not name.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from lonora_core.search_fold import fold
from lonora_core.user_error import ToolRefusal

MAXIMUM_CANDIDATES = 8
MAXIMUM_TEXT = 240
# Shorter than this, a name is contained in almost anything.
MINIMUM_PARTIAL = 3
ONE_FITS = (
    "Not found as written. One item fits and is listed: if it is the one the owner "
    "meant, repeat the call with its id. Do not ask the owner for an id."
)
ASK_WHICH = (
    "Several of the owner's own items fit. Never choose one: ask the owner which, "
    "describing each in plain words and never by its id, then repeat the call with the "
    "id of the one chosen."
)
NOTHING_FITS = (
    "Nothing of the owner's fits that. What exists is listed; if none of it is what the "
    "owner meant, say so plainly. Never invent an id."
)

# "any": a read. "exact": a stop of the caller's own item. "refuse": everything else.
Use = Literal["any", "exact", "refuse"]


@dataclass(frozen=True)
class Option:
    """One thing the caller may name: its id, what the owner might call it, what tells it apart."""

    id: str
    labels: tuple[str, ...]
    facts: dict[str, Any] = field(default_factory=dict[str, Any])


class NotResolved(ToolRefusal):
    """``<kind>_not_found`` or ``<kind>_ambiguous`` with what the model needs to go on."""


def _shown(option: Option, **extra: Any) -> dict[str, Any]:
    label = next((text for text in option.labels if text.strip()), "")
    return {"id": option.id, "label": label[:MAXIMUM_TEXT], **option.facts, **extra}


def _refusal(
    code: str,
    requested: str,
    argument: str,
    *,
    hint: str,
    retryable: bool,
    next_actions: list[dict[str, Any]],
    candidates: list[dict[str, Any]] | None = None,
    existing: list[dict[str, Any]] | None = None,
) -> NotResolved:
    details: dict[str, Any] = {
        "class": "resolution",
        "retryable": retryable,
        "hint": hint,
        "argument": argument,
        "requested": requested[:MAXIMUM_TEXT],
        "candidates": (candidates or [])[:MAXIMUM_CANDIDATES],
        "next_actions": next_actions,
    }
    if existing:
        details["existing"] = existing[:MAXIMUM_CANDIDATES]
    return NotResolved(code, 404, details=details)


def _matches(requested: str, options: Sequence[Option]) -> tuple[list[tuple[Option, str]], bool]:
    """The options a name fits, each with the label that fitted, and whether the fit is exact."""
    wanted = fold(requested)
    labelled = [(option, label, fold(label)) for option in options for label in option.labels]
    found = [(option, label) for option, label, name in labelled if name and name == wanted]
    exact = bool(found)
    if not found and len(wanted) >= MINIMUM_PARTIAL:
        found = [
            (option, label)
            for option, label, name in labelled
            if len(name) >= MINIMUM_PARTIAL and (wanted in name or name in wanted)
        ]
    once: dict[str, tuple[Option, str]] = {}
    for option, label in found:
        once.setdefault(option.id, (option, label))
    return list(once.values()), exact


def _telling(word: str) -> bool:
    """A word long enough to tell two names apart: "the" and "في" are shared by most."""
    return len(word) >= (4 if word.isascii() else 3)


def several(code: str, requested: str, argument: str, options: Sequence[Option]) -> NotResolved:
    """The refusal for more than one item: the caller never chooses between them."""
    return _refusal(
        code,
        requested,
        argument,
        hint=ASK_WHICH,
        retryable=False,
        next_actions=[{"ask_owner": "which_one"}],
        candidates=[_shown(option) for option in options],
    )


def resolve(
    requested: str,
    options: Sequence[Option],
    *,
    missing: str,
    argument: str,
    use: Use,
    listing: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """The id ``requested`` stands for, and the note to state when it was a name.

    ``missing`` is the tool's own not-found code; ``listing`` is the tool that lists what
    exists, named in the refusal when nothing fits.
    """
    for option in options:
        # The same id whatever its letter case.
        if option.id.casefold() == requested.strip().casefold():
            return option.id, None
    found, exact = _matches(requested, options)
    if len(found) == 1 and (use == "any" or (use == "exact" and exact)):
        option, label = found[0]
        return option.id, {
            "argument": argument,
            "requested": requested[:MAXIMUM_TEXT],
            "id": option.id,
            "label": label[:MAXIMUM_TEXT],
        }
    if len(found) == 1:
        option = found[0][0]
        raise _refusal(
            missing,
            requested,
            argument,
            hint=ONE_FITS,
            retryable=True,
            next_actions=[{"repeat_with": {argument: option.id}}],
            candidates=[_shown(option)],
        )
    if found:
        raise several(
            missing.removesuffix("_not_found") + "_ambiguous",
            requested,
            argument,
            [option for option, _ in found],
        )
    words = {word for word in fold(requested).split() if _telling(word)}
    near = [
        option
        for option in options
        if words & {word for label in option.labels for word in fold(label).split()}
    ]
    raise _refusal(
        missing,
        requested,
        argument,
        hint=NOTHING_FITS,
        retryable=False,
        next_actions=[{"tool": listing}] if listing else [],
        candidates=[_shown(option, similar=True) for option in near],
        existing=[] if near else [_shown(option) for option in options],
    )


def stating(result: dict[str, Any], *notes: dict[str, Any] | None) -> dict[str, Any]:
    """``result`` with what was taken from a name, so the model says which item it was."""
    said = [note for note in notes if note]
    if not said:
        return result
    return {**result, "resolved": [*result.get("resolved", []), *said]}
