from decimal import Decimal
from typing import Literal

from pydantic import Field

from .domain import Contract


class Watch(Contract):
    account_id: str
    symbol: str
    condition: Literal["above", "below", "cross_above", "cross_below"]
    level: Decimal = Field(gt=0)
    prompt: str = Field(min_length=1, max_length=8000)
    enabled: bool = True
    cooldown_seconds: int = Field(default=300, ge=30)
    interval_seconds: int = Field(default=30, ge=5)
