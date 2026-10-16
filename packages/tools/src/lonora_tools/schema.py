import re
from typing import Any

from lonora_core.user_error import LonoraError
from pydantic import BaseModel, ValidationError


class ToolArgumentsError(LonoraError):
    """Bounded machine guidance without submitted values, secrets or validator context."""

    def __init__(self, error: ValidationError):
        super().__init__("tool_arguments_invalid", 422)
        self.issues: list[dict[str, Any]] = []
        for item in error.errors(include_input=False, include_context=False, include_url=False)[
            :12
        ]:
            issue: dict[str, Any] = {
                "path": [
                    part
                    if isinstance(part, int)
                    or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", str(part))
                    else "[field]"
                    for part in item["loc"][:12]
                ],
                "type": item["type"],
            }
            # Our validators use stable machine codes; arbitrary exception text
            # is never copied to the model or user-visible event stream.
            match = re.fullmatch(r"Value error, ([a-z][a-z0-9_]{2,80})", item["msg"])
            if match:
                issue["code"] = match.group(1)
            self.issues.append(issue)


def validate_arguments(model: type[BaseModel], arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        return model.model_validate(arguments).model_dump(mode="json")
    except ValidationError as error:
        raise ToolArgumentsError(error) from None
