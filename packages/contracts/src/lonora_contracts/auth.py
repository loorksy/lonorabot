from pydantic import Field

from .domain import Contract


class LoginRequest(Contract):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)


class OnboardingRequest(LoginRequest):
    bootstrap_token: str = Field(min_length=24, max_length=256)


class SessionInfo(Contract):
    owner_id: str
    email: str
    expires_at: str
