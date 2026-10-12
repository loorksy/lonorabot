import hashlib
import secrets
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


async def authorization_url(
    endpoint: str, client_id: str, redirect_uri: str, state: str, challenge: str
) -> str:
    await validate_public_url(endpoint)
    return (
        endpoint
        + "?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )


async def exchange_code(
    endpoint: str, client_id: str, code: str, verifier: str, redirect_uri: str
) -> dict[str, str]:
    await validate_public_url(endpoint)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.post(
            endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
            },
        )
        if response.is_error:
            raise LonoraError("mcp_oauth_failed", 502)
        return response.json()
