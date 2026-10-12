from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator


def validate_id(value: str) -> str:
    return str(UUID(value))


EntityId = Annotated[str, AfterValidator(validate_id)]
