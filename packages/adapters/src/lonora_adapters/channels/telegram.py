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

    async def updates(self, offset: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get(
                    "https://api.telegram.org/bot" + self.token + "/getUpdates",
                    params={"offset": offset, "timeout": 0, "limit": 100},
                )
                value = response.json()
                if response.is_error or not value.get("ok"):
                    raise LonoraError("telegram_poll_failed", 502)
                return value["result"]
            except (httpx.HTTPError, ValueError):
                raise LonoraError("telegram_poll_failed", 502) from None
