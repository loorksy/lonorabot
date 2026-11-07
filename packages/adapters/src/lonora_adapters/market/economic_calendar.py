from typing import Any, cast

import httpx
from lonora_contracts.market import CalendarEvent
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url


class EconomicCalendarAdapter:
    def __init__(self, url: str):
        self.url = url

    async def events(self) -> list[CalendarEvent]:
        """Events from one source; every failure is a ``LonoraError`` without the URL."""
        url = await validate_public_url(self.url)
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                response = await client.get(url)
        except httpx.TimeoutException:
            raise LonoraError("calendar_source_timeout", 504) from None
        except httpx.HTTPError:
            # Transport messages can echo the configured URL, which may carry a token.
            raise LonoraError("calendar_source_unavailable", 502) from None
        if response.is_error:
            raise LonoraError("calendar_source_unavailable", 502)
        try:
            payload = response.json()
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
