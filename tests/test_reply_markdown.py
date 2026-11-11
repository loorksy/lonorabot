"""Bold markers with a space inside render as bold; everything else is untouched."""

import pytest
from lonora_agent.reply_markdown import normalize_bold


@pytest.mark.parametrize(
    ("written", "shown"),
    [
        # Message [16] of the owner's conversation.
        (
            "الذهب الآن عند **4049.73 / 4049.97**، والسبريد ** 0.24**.",
            "الذهب الآن عند **4049.73 / 4049.97**، والسبريد  **0.24**.",
        ),
        # The patterns of message [35].
        ("- ** جني الربح:** عند +2$", "-  **جني الربح:** عند +2$"),
        ("- **وقف الخسارة **عند -1$", "- **وقف الخسارة** عند -1$"),
        ("** أمر إغلاق مشروط **", " **أمر إغلاق مشروط** "),
        ("**a ** and ** b**", "**a**  and  **b**"),
    ],
)
def test_a_space_inside_the_markers_moves_outside(written: str, shown: str) -> None:
    assert normalize_bold(written) == shown
    assert normalize_bold(shown) == shown


@pytest.mark.parametrize(
    "text",
    [
        "**سليم** و*مائل* و__أيضًا__",
        "السعر `** 0.24**` كما كُتب",
        "``a ** b ** c``",
        "```\nx = 2 ** 3 ** 2\n```",
        "~~~python\nprint(** kwargs **)\n~~~",
        "**\nسطران\n**",
        "* بند\n* بند آخر",
        "****",
        "** **",
        "لا شيء هنا",
    ],
)
def test_code_and_valid_markdown_are_left_as_written(text: str) -> None:
    assert normalize_bold(text) == text
