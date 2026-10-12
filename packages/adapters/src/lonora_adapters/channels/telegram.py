from typing import Any

import httpx
from lonora_core.user_error import LonoraError


class TelegramAdapter:
    def __init__(self, token: str):
        self.token = token

    async def send(self, destination: str, content: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.telegram.org/bot" + self.token + "/sendMessage",
                json={"chat_id": destination, "text": content[:4096]},
            )
            value = response.json()
            if response.is_error or not value.get("ok"):
                raise LonoraError("telegram_delivery_failed", 502)
            return {"message_id": value["result"]["message_id"]}
