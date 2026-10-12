from typing import Any

from lonora_core.user_error import LonoraError
from pydantic import BaseModel, ValidationError


def validate_arguments(model: type[BaseModel], arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        return model.model_validate(arguments).model_dump(mode="json")
    except ValidationError:
        raise LonoraError("tool_arguments_invalid", 422) from None
