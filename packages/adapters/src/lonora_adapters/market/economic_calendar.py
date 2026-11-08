import json
from typing import Any, cast

import httpx
from lonora_contracts.market import CalendarEvent
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url

# A calendar feed is small; a larger body is refused before it is parsed (as web_fetch).
MAXIMUM_RESPONSE_BYTES = 2 * 1024 * 1024


class EconomicCalendarAdapter:
    def __init__(self, url: str):
        self.url = url

    async def events(self) -> list[CalendarEvent]:
        """Events from one source; every failure is a ``LonoraError`` without the URL."""
        url = await validate_public_url(self.url)
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                async with client.stream("GET", url) as response:
                    if response.is_error:
                        raise LonoraError("calendar_source_unavailable", 502)
                    # Streamed under a byte cap: a hostile host cannot exhaust memory.
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAXIMUM_RESPONSE_BYTES:
                            raise LonoraError("calendar_response_invalid", 502)
                        chunks.append(chunk)
        except httpx.TimeoutException:
            raise LonoraError("calendar_source_timeout", 504) from None
        except httpx.HTTPError:
            # Transport messages can echo the configured URL, which may carry a token.
            raise LonoraError("calendar_source_unavailable", 502) from None
        try:
            payload = json.loads(b"".join(chunks))
        except ValueError:  # A non-JSON body such as an HTML error page.
            raise LonoraError("calendar_response_invalid", 502) from None
        if not isinstance(payload, list):
            raise LonoraError("calendar_response_invalid", 502)
        try:
            return [
                CalendarEvent.model_validate(value) for value in cast(list[Any], payload)[:1000]
            ]
        except ValueError:  # A malformed event (pydantic ValidationError).
            raise LonoraError("calendar_response_invalid", 502) from None
