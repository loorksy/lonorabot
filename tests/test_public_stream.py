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
