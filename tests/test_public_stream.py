"""Privacy and effect claims gate streaming; catalog wording does not."""

import pytest
from lonora_agent.public_stream import PublicStream


def test_safe_sentences_arrive_before_completion():
    stream = PublicStream({"trade_execute"}, set(), enabled=True)
    text = (
        "Market observations remain provisional while additional evidence is being reviewed carefully. "
        * 2
    )
    assert stream.feed(text) == text
    assert stream.sent == text


@pytest.mark.parametrize(
    "text",
    [
        "My tools include market_quote and workspace_execute. ",
        "أدواتي تشمل قراءة السوق وتحليل الملفات. ",
        "The API emitted an event; broker_reconciliation_pending is a diagnostic code. ",
    ],
)
def test_catalog_and_technical_vocabulary_can_stream(text: str):
    stream = PublicStream({"market_quote", "workspace_execute"}, set(), enabled=True)
    assert stream.feed(text) == text
    assert stream.sent == text


@pytest.mark.parametrize(
    "text",
    [
        "The position was opened. ",
        "تم تنفيذ الطلب. ",
        "Record aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee. ",
        "The report is at /mnt/data/private.csv. ",
        "Bearer abcdefghijklmnopqrstuvwxyz0123456789 ",
    ],
)
def test_actual_private_material_and_effect_claims_are_not_admitted(text: str):
    stream = PublicStream({"trade_execute"}, set(), enabled=True)
    assert stream.feed(text * 20) == ""
    assert stream.sent == ""


def test_financial_context_can_disable_incremental_publication():
    stream = PublicStream(set(), set(), enabled=False)
    assert stream.feed("A public sentence. " * 20) == ""


def test_throttled_private_suffix_is_checked_before_next_publication(
    monkeypatch: pytest.MonkeyPatch,
):
    now = [0.0]
    monkeypatch.setattr("lonora_agent.public_stream.monotonic", lambda: now[0])
    stream = PublicStream({"trade_execute"}, set(), enabled=True)
    assert stream.feed("A welcome message. ")
    assert not stream.feed("File /mnt/data/private.csv. ")
    now[0] = 0.3
    assert not stream.feed("Further details. ")
    assert stream.sent == "A welcome message. "


def test_fragmented_private_identifier_cannot_leave_after_its_first_complete_word():
    stream = PublicStream(set(), set(), enabled=True)
    assert stream.feed("aaaaaaaa-bbbb-") == ""
    assert stream.feed("4ccc-8ddd-") == ""
    assert stream.feed("eeeeeeeeeeee ") == ""
    assert stream.sent == ""


def test_verified_broker_identifier_is_not_a_private_resource():
    identity = "11111111-2222-4333-8444-555555555555"
    text = "Broker ticket " + identity + " remains visible. "
    stream = PublicStream(set(), {identity}, enabled=True)
    assert stream.feed(text) == text
