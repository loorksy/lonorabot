from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from .domain import Contract, new_id

# The agent's one trading switch (mandate 4.1): "full" executes on its own and reports
# afterwards; "ask" raises a Trade Approval card for every risk-increasing request.
TradingMode = Literal["full", "ask"]


class TradingControl(Contract):
    enabled: bool = False
    emergency_stop: bool = False


class TradeRequest(Contract):
    thesis_id: str | None = Field(default=None, max_length=36)
    account_id: str = Field(min_length=1, max_length=120)
    operation_id: str = Field(default_factory=new_id, min_length=1, max_length=80)
    action: Literal[
        "buy",
        "sell",
        "buy_limit",
        "sell_limit",
        "buy_stop",
        "sell_stop",
        "close_position",
        "modify_position",
        "cancel_order",
        "modify_order",
    ]
    symbol: str = Field(min_length=1, max_length=80)
    volume: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    clear_stop_loss: bool = False
    clear_take_profit: bool = False
    position_id: str | None = None
    order_id: str | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "TradeRequest":
        if (
            self.clear_stop_loss
            and self.stop_loss is not None
            or self.clear_take_profit
            and self.take_profit is not None
        ):
            raise ValueError("conflicting_protection_edit")
        if (self.clear_stop_loss or self.clear_take_profit) and self.action not in {
            "modify_order",
            "modify_position",
        }:
            raise ValueError("protection_clear_requires_modification")
        if (
            self.action in {"modify_order", "modify_position"}
            and not any(
                value is not None
                for value in (
                    self.price if self.action == "modify_order" else None,
                    self.stop_loss,
                    self.take_profit,
                )
            )
            and not (self.clear_stop_loss or self.clear_take_profit)
        ):
            raise ValueError("modification_fields_required")
        if (
            self.action in {"modify_order", "modify_position", "cancel_order"}
            and self.volume is not None
        ):
            raise ValueError("volume_not_supported_for_modification")
        if (
            self.action in {"buy", "sell", "modify_position", "cancel_order", "close_position"}
            and self.price is not None
        ):
            raise ValueError("price_not_supported_for_action")
        if (
            self.action in {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"}
            and self.volume is None
        ):
            raise ValueError("volume_required")
        if (
            self.action in {"buy_limit", "sell_limit", "buy_stop", "sell_stop"}
            and self.price is None
        ):
            raise ValueError("price_required")
        if self.position_id and "position" not in self.action:
            raise ValueError("position_not_supported_for_action")
        if self.order_id and "order" not in self.action:
            raise ValueError("order_not_supported_for_action")
        if "position" in self.action and not self.position_id:
            raise ValueError("position_required")
        if "order" in self.action and not self.order_id:
            raise ValueError("order_required")
        return self


# The agent's judgment label (5.5.3): a slug it chooses, never a fixed list; "" is none.
LABEL_PATTERN = r"^[a-z0-9_]{0,40}$"


class TradeAnnotation(Contract):
    """The agent's own words about a request, stored beside it (mandate 14.3.9): never part
    of the request, its fingerprint or its operation id. Two sends that differ only in
    reason or label are the same operation."""

    reason: str = Field(default="", max_length=500)
    # A price distance in the symbol's price units: a card drifts outside reference ± it.
    tolerance: Decimal | None = Field(default=None, gt=0)
    label: str = Field(default="", pattern=LABEL_PATTERN)


# trade_execute's input: the request and, beside it, the agent's reason, tolerance, key
# and label. No docstring: it would be sent to the model with every eager schema.
class AnnotatedTradeRequest(TradeRequest):
    reason: str = Field(default="", max_length=500, description="Your one-line why.")
    tolerance: Decimal | None = Field(
        default=None,
        gt=0,
        description="± price distance from now a card holds.",
    )
    key: str | None = Field(
        default=None, min_length=1, max_length=64, description="New key: new order."
    )
    label: str = Field(default="", pattern=LABEL_PATTERN, description="e.g. scale_in")


# Durable operation lifecycle, distinct from any one broker's vocabulary:
# reserved   identity journaled; the send boundary was provably not crossed. Only the
#            executor's send boundary moves it to submitted, under the journal row lock.
# submitted  the send boundary authorized the broker mutation; it may have been sent.
# confirmed  the broker acknowledged it, or broker evidence later established it.
# failed     a known outcome: rejected by the broker, blocked before sending, never sent
#            (details.send_state == "not_sent"), or the requested target state is
#            observed not to hold.
# ambiguous  possibly sent, outcome not established; never resent automatically.
# resolved   the uncertainty is settled without establishing the operation's own outcome:
#            the owner recorded an audited attestation, or broker state shows the target
#            no longer exists, so the operation can no longer affect the account. It is
#            never broker confirmation; the earlier receipt and evidence are retained.
OperationStatus = Literal["reserved", "submitted", "confirmed", "failed", "ambiguous", "resolved"]
IN_PROGRESS_STATUSES = frozenset({"reserved", "submitted"})
# Possibly sent and not settled: these block new risk on the same market or ticket.
UNRESOLVED_STATUSES = frozenset({"submitted", "ambiguous"})
TERMINAL_STATUSES = frozenset({"confirmed", "failed", "resolved"})


class TradeResult(Contract):
    operation_id: str
    status: OperationStatus
    broker_id: str | None = None
    code: str | None = None
    details: dict[str, Any] = Field(default_factory=dict[str, Any])


# Recorded when the owner settles an operation without writing a note.
OWNER_ATTESTATION = "Owner attested; not broker confirmation."


class OperationResolution(Contract):
    """Owner attestation for an operation whose outcome broker evidence cannot establish.

    ``outcome`` is the owner's statement of fact (for example after checking the broker
    terminal), recorded with the actor and time. It settles the block; it never becomes
    broker confirmation and never triggers a resend.
    """

    outcome: Literal["executed", "not_executed", "unknown"]
    # Optional: without a note the record states that it is the owner's attestation.
    statement: str = Field(default="", max_length=2000)
    broker_reference: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def substantive(self) -> "OperationResolution":
        self.statement = self.statement.strip() or OWNER_ATTESTATION
        self.broker_reference = (self.broker_reference or "").strip() or None
        return self
