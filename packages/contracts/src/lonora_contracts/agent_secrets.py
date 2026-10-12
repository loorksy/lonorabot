from pydantic import Field

from .domain import Contract


class SecretCreate(Contract):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=16000)
