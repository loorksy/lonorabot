from typing import Literal

from pydantic import Field

from .domain import Contract


class BrokerConnection(Contract):
    provider: Literal["metaapi", "simulation"]
    account_id: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=80)
    secret_id: str | None = None
    enabled: bool = False
