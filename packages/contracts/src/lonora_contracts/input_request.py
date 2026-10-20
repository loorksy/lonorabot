"""Informational Agent questions. These contracts never confer execution authority."""

from pydantic import Field

from .domain import Contract


class InputChoice(Contract):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=240)
