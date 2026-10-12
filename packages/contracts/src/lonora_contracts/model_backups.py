from pydantic import Field

from .domain import Contract
from .model_routing import ModelSelection


class ModelBackups(Contract):
    choices: list[ModelSelection] = Field(default_factory=list[ModelSelection], max_length=3)
