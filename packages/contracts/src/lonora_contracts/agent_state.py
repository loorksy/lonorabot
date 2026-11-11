"""One truthful, bounded projection consumed by chat, voice and both clients."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .domain import Contract

CurrentWorkKind = Literal["analysing", "searching", "watching", "broker", "waiting_owner", "other"]


class CurrentWork(Contract):
    """What the agent does now, most urgent first (a card for the owner, an order at the
    broker, a running Run, an active watch), derived from durable records only."""

    kind: CurrentWorkKind
    # Owner content only: the Task's title, the owner's message a running reply answers or
    # the watched market; never a prompt, a tool body or server-written prose. An order at
    # the broker or a trade approval is described by ``operation`` (codes and numbers);
    # the clients word it in the owner's language.
    text: str = Field(default="", max_length=120)
    until: datetime | None = None
    run_id: str | None = None
    # broker / waiting_owner: the operation's action code, volume and market.
    operation: dict[str, str] | None = None
    # waiting_owner: what waits, "trade_approval" or "owner_action".
    card: Literal["trade_approval", "owner_action"] | None = None


class AgentLiveState(Contract):
    agent_id: str
    observed_at: datetime
    state: Literal["idle", "working", "waiting", "action_required", "degraded", "paused"]
    phase: str
    reason_code: str | None = None
    reason_params: dict[str, str | int] = Field(default_factory=dict[str, str | int])
    tasks: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=3)
    runs: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)
    runtime_waits: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)
    pending_approval_count: int = 0
    watch_count: int = 0
    # The agent's active watches (condition, market, expiry), newest first; never prompts.
    watches: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)
    pending_authorization_count: int = 0
    account_authorities: list[dict[str, Any]] = Field(
        default_factory=list[dict[str, Any]], max_length=3
    )
    collaborations: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=3)
    health: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)
    # Presentation only (lonora_db.trading_readiness): can it trade now, and what stops
    # it. Never consulted for enforcement; the executor re-checks at the moment of send.
    trading_readiness: dict[str, Any] | None = None
    current_work: CurrentWork | None = None
    # The newest pending owner-action card or trade approval waiting for the owner.
    pending_card_id: str | None = None
