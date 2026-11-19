from pydantic import Field

from .domain import Contract

# A workspace secret is used by name: the environment variable NAME and /run/secrets/NAME.
WORKSPACE_SECRET_NAME = r"^[A-Z][A-Z0-9_]{0,63}$"


class SecretCreate(Contract):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=16000)
