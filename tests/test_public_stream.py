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


def test_private_text_and_effect_claims_are_not_admitted():
    for text in [
        "I used trade_execute. ",
        "The position was opened. ",
        "تم تنفيذ الطلب. ",
        "أرسلت بطاقة عبر API. ",
    ]:
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
    assert not stream.feed("I used trade_execute. ")
    now[0] = 0.3
    assert not stream.feed("Further details. ")
    assert stream.sent == "A welcome message. "
