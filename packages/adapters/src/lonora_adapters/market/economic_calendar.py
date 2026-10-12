import httpx
from lonora_contracts.market import CalendarEvent
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url


class EconomicCalendarAdapter:
    def __init__(self, url: str):
        self.url = url

    async def events(self) -> list[CalendarEvent]:
        url = await validate_public_url(self.url)
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(url)
            if response.is_error:
                raise LonoraError("calendar_source_unavailable", 502)
            payload = response.json()
            if not isinstance(payload, list):
                raise LonoraError("calendar_response_invalid", 502)
            return [CalendarEvent.model_validate(value) for value in payload[:1000]]
