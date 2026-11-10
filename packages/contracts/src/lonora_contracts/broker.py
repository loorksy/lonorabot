from typing import Literal

from pydantic import Field

from .domain import Contract


class BrokerConnection(Contract):
    # Alpaca is the paper trading host only; live trading is a later owner decision.
    provider: Literal["metaapi", "simulation", "alpaca"]
    account_id: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=80)
    secret_id: str | None = None
    enabled: bool = False


# Providers whose connection is created only from a broker-observed identity.
VERIFIED_PROVIDERS = frozenset({"metaapi", "alpaca"})
