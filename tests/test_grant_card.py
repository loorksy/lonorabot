"""Grant cards and the monotonic ladder: pure rules, no database (W15-3)."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_contracts.account_authority import AccountAuthorityEnvelope, full_delegation
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import (
    DailyLossDraft,
    GrantDraft,
    OwnerActionDecision,
    OwnerActionProposal,
)
from lonora_contracts.risk_limits import MonetaryRiskLimits
from lonora_core.delegation_words import asks_full_delegation
from lonora_db.agent_permissions import default_level
from lonora_db.owner_actions import (
    ALL_ACTIONS,
    covers_draft,
    daily_loss_change,
    grant_proposal,
    grant_terms,
    overlaps_draft,
    requested_above,
    widens,
)
from lonora_db.schema import AgentRow
from pydantic import ValidationError


def draft(**changes: Any) -> GrantDraft:
    values: dict[str, Any] = {
        "agent_id": "gold",
        "account_id": "acct",
        "symbol_scope": "selected",
        "symbols": ["XAUUSD"],
        "actions": list(ALL_ACTIONS),
        "daily_loss": DailyLossDraft(
            amount=Decimal("300"), currency="USD", basis="suggested", percent=Decimal(3)
        ),
    }
    values.update(changes)
    return GrantDraft(**values)


def envelope(**changes: Any) -> AccountAuthorityEnvelope:
    values: dict[str, Any] = {
        "thread_id": "thread",
        "account_id": "acct",
        "management_mode": "full",
        "symbol_scope": "selected",
        "symbols": ["XAUUSD"],
        "actions": list(ALL_ACTIONS),
        "owner_id": "owner",
        "agent_id": "gold",
        "schema_version": 2,
    }
    values.update(changes)
    return AccountAuthorityEnvelope(**values)


def agent(role: str, parent: str | None = None) -> AgentRow:
    return cast(AgentRow, SimpleNamespace(role=role, parent_id=parent))


def test_ladder_defaults_follow_the_template() -> None:
    assert default_level(agent("personal")) == "supervised"
    assert default_level(agent("specialist")) == "supervised"
    for role, parent in (("general", None), ("legacy", None), ("delegated", "p")):
        assert default_level(agent(role, parent)) == "analysis"
    # A bound child is a helper of its parent: it never starts at Ask me.
    assert default_level(agent("specialist", "parent")) == "analysis"


def test_a_grant_proposal_is_built_only_from_the_stored_draft() -> None:
    now = utcnow()
    signed = grant_proposal(draft(), "thread", now)
    assert signed.model_dump(mode="json") == {
        "thread_id": "thread",
        "account_id": "acct",
        "management_mode": "full",
        "symbol_scope": "selected",
        "symbols": ["XAUUSD"],
        "actions": list(ALL_ACTIONS),
        "maximum_order_volume": None,
        "maximum_symbol_volume": None,
        "maximum_positions": None,
        "maximum_pending_orders": None,
        "maximum_actions": None,
        "minimum_equity": None,
        "valid_until": None,
        # Owner decision D1: the owner's own positions are excluded unless switched on.
        "allow_manual_positions": False,
    }
    timed = grant_proposal(draft(duration="24h"), "thread", now)
    assert timed.valid_until == now + timedelta(hours=24)
    every_pair = grant_proposal(draft(symbol_scope="account", symbols=[]), "thread", now)
    assert every_pair.symbol_scope == "account" and every_pair.symbols == []
    with pytest.raises(ValidationError):
        draft(symbol_scope="account")  # All pairs never also lists symbols.
    with pytest.raises(ValidationError):
        draft(symbols=[])


def requested(amount: str, percent: str | None = None) -> GrantDraft:
    return draft(
        daily_loss=DailyLossDraft(
            amount=Decimal(amount),
            currency="USD",
            basis="requested",
            percent=None if percent is None else Decimal(percent),
        )
    )


def test_a_suggested_daily_loss_is_set_only_where_the_account_has_none() -> None:
    unset = MonetaryRiskLimits()
    first = daily_loss_change(unset, draft())
    assert first is not None and first.max_daily_loss == 300 and first.currency == "USD"
    assert not widens(unset, first)
    # The owner set 500 themselves: the suggested 3% (300) never tightens it unasked.
    own = MonetaryRiskLimits(currency="USD", max_daily_loss=Decimal(500))
    assert daily_loss_change(own, draft()) is None
    assert requested_above(own, draft()) is None
    # Another currency is never converted.
    euro = MonetaryRiskLimits(currency="EUR", max_trade_risk=Decimal(50))
    assert daily_loss_change(euro, draft()) is None
    assert daily_loss_change(unset, draft(daily_loss=None)) is None


def test_the_owners_own_daily_loss_lowers_a_limit_and_never_raises_one() -> None:
    own = MonetaryRiskLimits(currency="USD", max_daily_loss=Decimal(500))
    lowered = daily_loss_change(own, requested("300", "3"))
    assert lowered is not None and lowered.max_daily_loss == 300 and not widens(own, lowered)
    assert requested_above(own, requested("300")) is None
    # Asking for more keeps the current limit; raising it is a limits card's passkey.
    assert daily_loss_change(own, requested("800")) is None
    assert requested_above(own, requested("800")) == 800
    assert daily_loss_change(own, requested("500")) is None
    assert requested_above(own, requested("500")) is None
    first = daily_loss_change(MonetaryRiskLimits(), requested("800"))
    assert first is not None and first.max_daily_loss == 800
    assert requested_above(MonetaryRiskLimits(), requested("800")) is None


def test_the_replaced_grant_is_described_in_full() -> None:
    capped = envelope(
        management_mode="bounded",
        symbols=["XAUUSD", "EURUSD"],
        actions=["buy", "sell", "close_position"],
        maximum_order_volume=Decimal("0.5"),
        maximum_symbol_volume=Decimal(1),
        maximum_positions=3,
        maximum_pending_orders=0,
        maximum_actions=40,
        minimum_equity=Decimal(1000),
        valid_until=utcnow() + timedelta(days=2),
        schema_version=1,
    )
    terms = grant_terms(capped)
    assert terms["management_mode"] == "bounded" and terms["all_actions"] is False
    assert terms["symbols"] == ["XAUUSD", "EURUSD"]
    assert terms["maximum_order_volume"] == "0.5" and terms["maximum_positions"] == 3
    assert terms["maximum_pending_orders"] == 0 and terms["minimum_equity"] == "1000"
    assert terms["valid_until"] is not None and terms["allow_manual_positions"] is False
    assert not covers_draft(capped, draft())


def test_covered_scope_needs_no_card_and_overlap_is_named() -> None:
    assert covers_draft(envelope(), draft())
    assert covers_draft(envelope(symbol_scope="account", symbols=[]), draft())
    assert not covers_draft(envelope(), draft(symbols=["XAUUSD", "EURUSD"]))
    assert not covers_draft(envelope(actions=["buy"]), draft())
    assert not covers_draft(envelope(), draft(allow_manual_positions=True))
    assert not covers_draft(envelope(maximum_positions=3), draft())
    expiring = envelope(valid_until=utcnow() + timedelta(hours=2))
    assert not covers_draft(expiring, draft())
    assert overlaps_draft(envelope(symbols=["xauusd"]), draft())
    assert overlaps_draft(envelope(symbols=["EURUSD"]), draft(symbol_scope="account", symbols=[]))
    assert not overlaps_draft(envelope(symbols=["EURUSD"]), draft())


def test_grant_fields_belong_to_grant_cards_and_decisions_default_to_narrowing() -> None:
    proposal = OwnerActionProposal.model_validate(
        {"kind": "grant_authority", "agent_id": "gold", "daily_loss_percent": "2"}
    )
    assert proposal.account_id is None and proposal.daily_loss_percent == 2
    assert OwnerActionProposal.model_validate({"kind": "grant_authority"}).all_pairs is False
    with pytest.raises(ValidationError):
        OwnerActionProposal.model_validate({"kind": "resume_trading", "agent_id": "gold"})
    decision = OwnerActionDecision(decision="confirm")
    assert decision.money_limit == "apply"
    assert decision.resume_trading is False and decision.stop_authorities == []


def test_full_delegation_signs_every_pair_action_and_own_position_with_no_card_limit() -> None:
    custom = draft()
    full = custom.with_delegation("full")
    assert full.delegation == "full" and full.custom == custom.terms()
    signed = grant_proposal(full, "thread", utcnow())
    assert signed.model_dump(mode="json") == {
        "thread_id": "thread",
        "account_id": "acct",
        "management_mode": "full",
        "symbol_scope": "account",
        "symbols": [],
        "actions": list(ALL_ACTIONS),
        "maximum_order_volume": None,
        "maximum_symbol_volume": None,
        "maximum_positions": None,
        "maximum_pending_orders": None,
        "maximum_actions": None,
        "minimum_equity": None,
        # No expiry: until the owner stops it.
        "valid_until": None,
        "allow_manual_positions": True,
    }
    assert full_delegation(signed.model_dump(mode="json"))
    # The card sets no daily loss limit under Full, so it never touches the account's.
    assert full.daily_loss is None
    assert daily_loss_change(MonetaryRiskLimits(), full) is None
    own = MonetaryRiskLimits(currency="USD", max_daily_loss=Decimal(500))
    assert daily_loss_change(own, full) is None and requested_above(own, full) is None


def test_switching_back_restores_custom_exactly_with_the_d1_defaults() -> None:
    custom = draft()
    assert custom.delegation == "custom" and custom.custom is None
    assert custom.allow_manual_positions is False and custom.daily_loss is not None
    there = custom.with_delegation("full")
    back = there.with_delegation("custom")
    assert back == custom and back.model_dump(mode="json") == custom.model_dump(mode="json")
    # Back and forth again changes nothing, and the stored JSON round-trips.
    assert back.with_delegation("full") == there
    assert GrantDraft.model_validate(there.model_dump(mode="json")) == there
    assert custom.with_delegation("custom") is custom
    # A stored Full draft is always exactly the Full terms, with the Custom ones kept.
    with pytest.raises(ValidationError):
        GrantDraft.model_validate({**there.model_dump(mode="json"), "custom": None})
    with pytest.raises(ValidationError):
        GrantDraft.model_validate({**there.model_dump(mode="json"), "duration": "24h"})
    with pytest.raises(ValidationError):
        GrantDraft.model_validate(
            {**there.model_dump(mode="json"), "allow_manual_positions": False}
        )
    with pytest.raises(ValidationError):
        GrantDraft.model_validate(
            {**custom.model_dump(mode="json"), "custom": custom.terms().model_dump(mode="json")}
        )
    # A draft stored before the choice existed reads as Custom.
    legacy = custom.model_dump(mode="json")
    del legacy["delegation"], legacy["custom"]
    assert GrantDraft.model_validate(legacy) == custom


def test_full_delegation_is_recognized_only_with_every_term() -> None:
    full = envelope(symbol_scope="account", symbols=[], allow_manual_positions=True).model_dump(
        mode="json"
    )
    assert full_delegation(full)
    for changes in (
        {"allow_manual_positions": False},
        {"actions": ["buy", "sell"]},
        {"valid_until": (utcnow() + timedelta(days=1)).isoformat()},
        {"maximum_positions": 3},
        {"symbol_scope": "selected", "symbols": ["XAUUSD"]},
        {"management_mode": "bounded"},
    ):
        assert not full_delegation({**full, **changes}), changes
    # A signed Full grant covers both choices; a Custom grant never covers Full.
    signed_full = envelope(symbol_scope="account", symbols=[], allow_manual_positions=True)
    assert covers_draft(signed_full, draft().with_delegation("full"))
    assert covers_draft(signed_full, draft())
    assert not covers_draft(envelope(), draft().with_delegation("full"))
    assert grant_terms(signed_full)["full_delegation"] is True
    assert grant_terms(envelope())["full_delegation"] is False


def test_the_choice_is_a_grant_field_and_a_decision_that_signs_nothing() -> None:
    proposal = OwnerActionProposal.model_validate({"kind": "grant_authority", "delegation": "full"})
    assert proposal.delegation == "full" and proposal.grant_fields()
    with pytest.raises(ValidationError):
        OwnerActionProposal.model_validate({"kind": "resume_trading", "delegation": "full"})
    choose = OwnerActionDecision.model_validate({"decision": "choose", "delegation": "full"})
    assert choose.proof is None and choose.delegation == "full"
    with pytest.raises(ValidationError):
        OwnerActionDecision.model_validate({"decision": "choose", "delegation": "everything"})


@pytest.mark.parametrize(
    "words",
    [
        "فوّض وكيل الفضة تفويضًا كاملًا على حسابي",
        "أعطه تفويض كامل",
        "التفويض الكامل لوكيل الذهب",
        "فوضه بالكامل",
        "أعطِ لونورا كل الصلاحيات على حسابي",
        "صلاحيات التداول الكاملة",
        "صلاحية مطلقة على الحساب",
        "تحكم كامل بحسابي",
        "Give the gold agent full delegation",
        "I want to fully delegate my account",
        "delegate everything to it",
        "give it complete control",
        "full trading authority please",
        "carte blanche on my account",
    ],
)
def test_owner_words_asking_for_full_delegation(words: str) -> None:
    assert asks_full_delegation(words)


@pytest.mark.parametrize(
    "words",
    [
        "trade gold for me",
        "تداول الذهب عني من الآن",
        "give me a full analysis of gold",
        "تحليل كامل للذهب",
        "trade all pairs for me until I stop you",
        "إدارة المخاطر بشكل كامل",
        "open a full position on EURUSD",
        "خله يتداول بنفسه على الذهب",
        "",
    ],
)
def test_owner_words_not_asking_for_full_delegation(words: str) -> None:
    """A Full card opens only from the owner's words; anything else opens on Custom."""
    assert not asks_full_delegation(words)
