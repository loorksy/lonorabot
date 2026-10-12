import hashlib
import hmac
import json
from typing import Any

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url


class WebhookAdapter:
    def __init__(self, secret: str):
        self.secret = secret

    async def send(self, destination: str, content: str) -> dict[str, Any]:
        await validate_public_url(destination)
        body = json.dumps({"content": content}).encode()
        signature = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(
                destination,
                content=body,
                headers={"Content-Type": "application/json", "X-Lonora-Signature": signature},
            )
            if response.is_error:
                raise LonoraError("webhook_delivery_failed", 502)
            return {"status": response.status_code}
