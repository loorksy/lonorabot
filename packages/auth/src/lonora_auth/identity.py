from dataclasses import dataclass


@dataclass(frozen=True)
class OwnerIdentity:
    id: str
    email: str
    token_hash: str
