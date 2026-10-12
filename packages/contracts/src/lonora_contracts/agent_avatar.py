from typing import Literal

from pydantic import Field

from .domain import Contract


class Avatar(Contract):
    shape: Literal["orb", "circle", "square", "diamond"] = "orb"
    color: str = Field(default="#7c83fd", pattern=r"^#[0-9a-fA-F]{6}$")
