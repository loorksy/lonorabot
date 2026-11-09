"""Passkey enrollment and assertions; a device proof is never a grant by itself."""

from typing import Any

from pydantic import Field, SecretStr

from .domain import Contract


class DeviceEnrollment(Contract):
    password: SecretStr
    name: str = Field(min_length=1, max_length=80)


class DeviceProof(Contract):
    challenge_id: str
    credential: dict[str, Any]
