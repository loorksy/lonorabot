import json
from collections.abc import AsyncIterator
from typing import Any

import websockets
from lonora_core.user_error import LonoraError


class OpenAIRealtimeAdapter:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def events(self, model: str, instructions: str) -> AsyncIterator[dict[str, Any]]:
        from urllib.parse import quote

        try:
            async with websockets.connect(
                "wss://api.openai.com/v1/realtime?model=" + quote(model, safe=""),
                additional_headers={"Authorization": "Bearer " + self.api_key},
            ) as connection:
                await connection.send(
                    json.dumps(
                        {
                            "type": "session.update",
                            "session": {"type": "realtime", "instructions": instructions},
                        }
                    )
                )
                async for raw in connection:
                    event = json.loads(raw)
                    if isinstance(event, dict):
                        yield event
        except (OSError, websockets.WebSocketException):
            raise LonoraError("realtime_connection_failed", 502) from None
