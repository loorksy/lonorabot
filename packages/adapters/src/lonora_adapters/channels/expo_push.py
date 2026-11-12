"""The Expo push service (VISION 11.4): one HTTPS request per batch of at most 100 messages.

The owner's optional Expo access token authorizes the request when the Expo project requires
it. Results come back in the order of the messages; a request that fails or times out is an
unknown outcome for every message in it, and the caller never sends those again.
"""

from typing import Any

import httpx
from lonora_core.user_error import LonoraError

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_BATCH = 100
EXPO_TIMEOUT_SECONDS = 15


class ExpoPushTransport:
    def __init__(
        self, access_token: str | None = None, http: httpx.AsyncBaseTransport | None = None
    ):
        # ``http`` replaces the network in tests; production always uses the default.
        self.access_token, self.http = access_token, http

    async def send(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not 0 < len(messages) <= EXPO_BATCH:
            raise LonoraError("push_batch_invalid", 500)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = "Bearer " + self.access_token
        async with httpx.AsyncClient(
            timeout=EXPO_TIMEOUT_SECONDS, follow_redirects=False, transport=self.http
        ) as client:
            response = await client.post(EXPO_PUSH_URL, json=messages, headers=headers)
        # A 4xx is Expo refusing the request: nothing in it was accepted. A 5xx may have
        # been partly accepted, so its outcome is unknown.
        if 400 <= response.status_code < 500:
            raise LonoraError("push_request_refused", 502)
        if response.status_code >= 500:
            raise LonoraError("push_request_failed", 502)
        try:
            tickets = response.json()["data"]
        except (ValueError, KeyError, TypeError):
            raise LonoraError("push_response_invalid", 502) from None
        if not isinstance(tickets, list) or len(tickets) != len(messages):
            raise LonoraError("push_response_invalid", 502)
        return [ticket if isinstance(ticket, dict) else {} for ticket in tickets]
