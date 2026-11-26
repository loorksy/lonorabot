from pydantic import Field

from .domain import Contract


class LoginRequest(Contract):
    email: str = Field(min_length=3, max_length=254)
    # No minimum at sign-in: a Lonora Cloud owner keeps the website password, which may be shorter
    # (D7). Setting a password still needs 12 to 128 characters (account_security.hash_password).
    password: str = Field(min_length=1, max_length=128)


class OnboardingRequest(LoginRequest):
    bootstrap_token: str = Field(min_length=24, max_length=256)


class SessionInfo(Contract):
    owner_id: str
    email: str
    expires_at: str
