"""An Agent capability with explicit, signed goal authority; never a new Agent."""

from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, SecretStr

from .domain import Contract
from .trading_goal import GoalStep


class SuperBotEnvelope(Contract):
    goal_id: str
    account_id: str
    symbol: str
    plan_version: int
    plan_hash: str
    mode: Literal["advisory", "supervised", "autonomous"]
    maximum_volume: Decimal | None = None
    max_trade_actions: int
    allow_manual_positions: bool = False
    execution_mode: Literal["live", "shadow"] = "live"
    goal_title: str = ""
    objective: str = ""
    steps: list[GoalStep] = Field(default_factory=list[GoalStep], max_length=40)


class SuperBotProposal(Contract):
    goal_id: str
    mode: Literal["advisory", "supervised", "autonomous"] = "supervised"
    allow_manual_positions: bool = False


class SuperBotControl(Contract):
    request_id: str
    action: Literal["reject", "pause", "stop", "advisory", "supervised"]


class DeviceEnrollment(Contract):
    password: SecretStr
    name: str = Field(min_length=1, max_length=80)


class DeviceProof(Contract):
    challenge_id: str
    credential: dict[str, Any]
