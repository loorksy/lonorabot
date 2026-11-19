"""Owner integrations: search, calendar and news feeds, and message channels.

A channel delivers incoming messages to one agent's conversation: the owner picks the
agent (``deliver_to_agent_id``) and the conversation is resolved here, never typed as an
id. A news feed needs a public HTTPS URL; reading it goes through the SSRF-safe public
client at read time, which validates the address again.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from lonora_contracts.integrations import Integration
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import IntegrationRow
from .transactions import ResourceRepository
from .trusted_sources import feed_domain_of


def feed_host(url: str) -> str:
    """The trusted-list domain of a feed URL; raises ``news_feed_url_invalid``."""
    try:
        parsed = urlsplit(url)
        if (
            len(url) > 2048
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
            or any(ord(char) < 33 for char in url)
        ):
            raise ValueError
        return feed_domain_of(parsed.hostname)
    except ValueError:
        raise LonoraError("news_feed_url_invalid", 422) from None


# Sources whose address may carry a key: one saved from a Secret card keeps it in the
# encrypted store (``secret_id``) and only its host on the row (``domain``).
ADDRESSED = frozenset({"news_feed", "economic_calendar"})


def has_source(payload: dict[str, Any]) -> bool:
    """A feed or calendar that has an address to read."""
    return bool(
        payload.get("url") or (payload.get("type") in ADDRESSED and payload.get("secret_id"))
    )


def source_host(payload: dict[str, Any]) -> str | None:
    """A feed's or calendar's host, never its address (which may carry a key)."""
    if payload.get("domain"):
        return str(payload["domain"])
    return urlsplit(str(payload["url"])).hostname if payload.get("url") else None


def feed_site(payload: dict[str, Any]) -> str | None:
    """A news feed's trusted-list domain, from its URL or its stored host; None when it
    has neither or the URL is not a public HTTPS feed."""
    try:
        if payload.get("url"):
            return feed_host(str(payload["url"]))
        return feed_domain_of(str(payload["domain"])) if payload.get("domain") else None
    except (LonoraError, ValueError):
        return None


async def source_url(payload: dict[str, Any], read: Callable[[str], Awaitable[str]]) -> str:
    """A feed's or calendar's address: on the row, or read from the encrypted store. A
    stored address is used only while it is on the host the row was saved with, the
    host the owner's trust names."""
    if payload.get("url"):
        return str(payload["url"])
    address = (await read(str(payload["secret_id"]))).strip()
    try:
        host = urlsplit(address).hostname
    except ValueError:
        host = None
    if host is None or host != str(payload.get("domain") or "").lower():
        raise LonoraError("integration_source_changed", 409)
    return address


class IntegrationRepository(ResourceRepository):
    row_type = IntegrationRow
    payload_model = Integration
    kind = "integrations"
    # Its key or address: an owner's integration secret, or a workspace secret saved from
    # a Secret card. Never a broker or provider value.
    secret_scopes = ("integration", "workspace")

    async def validate_references(
        self, session: AsyncSession, owner_id: str, payload: dict[str, Any]
    ) -> None:
        await super().validate_references(session, owner_id, payload)
        if payload.get("type") in ADDRESSED and not payload.get("url"):
            # Saved from a Secret card: the address is in the store, its host is here.
            if not payload.get("secret_id") or not payload.get("domain"):
                raise LonoraError("integration_source_required", 422)
        elif payload.get("type") == "news_feed":
            feed_host(str(payload.get("url") or ""))
        agent_id = payload.get("deliver_to_agent_id")
        if agent_id:
            from .threads import conversation_thread

            # The chosen agent's own conversation receives the channel's messages.
            payload["thread_id"] = (await conversation_thread(session, owner_id, agent_id)).id


async def subscribed_feed(session: AsyncSession, owner_id: str, url: str) -> IntegrationRow | None:
    rows = await session.scalars(
        select(IntegrationRow).where(IntegrationRow.owner_id == owner_id).limit(500)
    )
    return next(
        (
            row
            for row in rows
            if row.payload.get("type") == "news_feed" and row.payload.get("url") == url
        ),
        None,
    )


async def subscribe_feed(
    session: AsyncSession, owner_id: str, url: str, name: str
) -> tuple[IntegrationRow, bool]:
    """One news feed every agent reads; the same URL twice is the same subscription."""
    feed_host(url)
    existing = await subscribed_feed(session, owner_id, url)
    if existing is not None:
        return existing, False
    created = await IntegrationRepository().create(
        session,
        owner_id,
        {
            "type": "news_feed",
            "name": name.strip()[:120] or "News feed",
            "url": url,
            "enabled": True,
        },
    )
    assert isinstance(created, IntegrationRow)
    return created, True
