"""Owner integrations: web search, calendar and news feeds, and message channels.

A ``news_feed`` is one RSS or Atom feed every agent reads with ``news_feed_read``; its
URL may carry a token, so agents see its name and domain, never the URL. A feed or a
calendar connected from a Secret card keeps its URL in the encrypted store (``secret_id``)
and only its ``domain`` here. Channels
deliver incoming messages to one agent's conversation, chosen by agent
(``deliver_to_agent_id``); the server keeps that conversation in ``thread_id``.
"""

from typing import Literal

from pydantic import Field

from .domain import Contract

IntegrationType = Literal["brave_search", "economic_calendar", "news_feed", "telegram", "webhook"]


class Integration(Contract):
    type: IntegrationType
    name: str = Field(max_length=200)
    url: str | None = Field(default=None, max_length=2048)
    secret_id: str | None = None
    domain: str | None = Field(default=None, max_length=253)
    enabled: bool = False
    thread_id: str | None = None
    deliver_to_agent_id: str | None = Field(default=None, max_length=36)
    allowed_destinations: list[str] = Field(default_factory=list[str])
