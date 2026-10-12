from typing import Literal

from pydantic import Field

from .domain import Contract


class BrokerConnection(Contract):
    provider: Literal["metaapi", "simulation"]
    account_id: str = Field(min_length=1, max_length=120)
    region: Literal["london", "new-york", "singapore"] = "london"
    secret_id: str | None = None
    enabled: bool = False
