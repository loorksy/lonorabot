"""Small contracts complement the real PostgreSQL conversation recall script."""

import pytest
from lonora_memory.conversation import ConversationRecallScope
from lonora_memory.evidence import Evidence, fuse_evidence


@pytest.mark.parametrize("input_seq,before_seq", [(-1, 0), (1, -1), (True, 0), (1, False)])
def test_recall_scope_rejects_invalid_cutoffs(input_seq: int, before_seq: int):
    with pytest.raises(ValueError, match="invalid_conversation_recall_scope"):
        ConversationRecallScope("thread", input_seq, before_seq)


def test_recall_scope_is_explicit_and_neighbor_is_opt_in():
    scope = ConversationRecallScope("thread", 12, 8)
    assert not scope.include_neighbor
    assert scope.before_seq == 8


def test_fusion_retains_historical_authority_without_financial_freshness():
    source = Evidence(
        "message:real-id",
        "conversation_message",
        "XAUUSDm prior evidence",
        0,
        "2026-01-01T00:00:00Z",
        {"message_id": "real-id", "seq": 4},
        authority="untrusted_historical_conversation",
    )
    items, truncated = fuse_evidence([source], "XAUUSDm", {}, maximum_chars=8)
    assert truncated and items[0].text == "XAUUSDm "
    assert items[0].authority == source.authority
    assert items[0].provenance == source.provenance
    assert items[0].freshness == "unknown" and items[0].source_time is None
