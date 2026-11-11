"""One resolver: the id itself, one item that fits, several, none."""

import pytest
from lonora_tools.resolve import NotResolved, Option, resolve, stating

WATCHES = [
    Option("w-1", ("EURUSD", "EURUSD above 1.10"), {"symbol": "EURUSD"}),
    Option("w-2", ("XAUUSDm", "الذهب فوق 4100"), {"symbol": "XAUUSDm"}),
    Option("w-3", ("", "no"), {}),
]


def refused(requested: str, options: list[Option], use: str) -> NotResolved:
    with pytest.raises(NotResolved) as failure:
        resolve(
            requested,
            options,
            missing="market_watches_not_found",
            argument="watch_id",
            use=use,  # type: ignore[arg-type]
            listing="watch_list",
        )
    return failure.value


def test_an_id_is_itself_and_nothing_is_stated() -> None:
    found = resolve("w-2", WATCHES, missing="x_not_found", argument="watch_id", use="refuse")
    assert found == ("w-2", None)
    assert stating({"ok": True}, None) == {"ok": True}


def test_a_read_uses_the_one_item_a_name_fits_and_says_so() -> None:
    # Arabic folds as the owner's search does: أ and ا, ة and ه, tashkeel.
    identifier, note = resolve(
        "الذَّهب فوق 4100", WATCHES, missing="x_not_found", argument="watch_id", use="any"
    )
    assert identifier == "w-2" and note == {
        "argument": "watch_id",
        "requested": "الذَّهب فوق 4100",
        "id": "w-2",
        "label": "الذهب فوق 4100",
    }
    assert stating({"cancelled": True}, note, None) == {"cancelled": True, "resolved": [note]}
    partial = resolve("eurusd abo", WATCHES, missing="x_not_found", argument="watch_id", use="any")
    assert partial[0] == "w-1"


def test_a_stop_uses_only_an_exact_name_and_a_change_never_uses_a_name() -> None:
    assert (
        resolve("eurusd", WATCHES, missing="x_not_found", argument="watch_id", use="exact")[0]
        == "w-1"
    )
    partial = refused("eurusd abo", WATCHES, "exact")
    assert partial.code == "market_watches_not_found" and partial.details["retryable"] is True
    assert partial.details["candidates"] == [{"id": "w-1", "label": "EURUSD", "symbol": "EURUSD"}]
    assert partial.details["next_actions"] == [{"repeat_with": {"watch_id": "w-1"}}]
    change = refused("EURUSD", WATCHES, "refuse")
    assert change.details["class"] == "resolution" and change.details["retryable"] is True
    assert change.details["next_actions"] == [{"repeat_with": {"watch_id": "w-1"}}]


def test_several_items_are_never_chosen_between() -> None:
    twice = [*WATCHES, Option("w-4", ("EURUSD", "EURUSD below 1.05"), {"symbol": "EURUSD"})]
    for use in ("any", "exact", "refuse"):
        several = refused("EURUSD", twice, use)
        assert several.code == "market_watches_ambiguous"
        assert several.details["retryable"] is False
        assert [item["id"] for item in several.details["candidates"]] == ["w-1", "w-4"]
        assert several.details["next_actions"] == [{"ask_owner": "which_one"}]


def test_nothing_fitting_lists_the_nearest_names_or_what_exists() -> None:
    near = refused("EURUSD breakout tomorrow", [Option("w-9", ("EURUSD hourly close",), {})], "any")
    assert near.code == "market_watches_not_found" and near.details["retryable"] is False
    assert near.details["candidates"] == [
        {"id": "w-9", "label": "EURUSD hourly close", "similar": True}
    ]
    assert "existing" not in near.details
    nothing = refused("bitcoin", WATCHES, "any")
    assert nothing.details["candidates"] == []
    assert [item["id"] for item in nothing.details["existing"]] == ["w-1", "w-2", "w-3"]
    assert nothing.details["next_actions"] == [{"tool": "watch_list"}]


def test_an_empty_or_very_short_name_fits_nothing() -> None:
    # An item with no name is not a match for every request, nor a two-letter one for most.
    assert refused("anything at all", WATCHES, "any").details["candidates"] == []
    assert (
        refused("no way", [Option("r-1", ("",), {}), Option("r-2", ("no",), {})], "any").details[
            "candidates"
        ]
        == []
    )
    assert refused("", WATCHES, "any").details["candidates"] == []
    # Exactly that short name is still its own.
    assert resolve("no", WATCHES, missing="x_not_found", argument="watch_id", use="any")[0] == "w-3"
