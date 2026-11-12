"""Owner integrations and the secret values they use, owner session only.

A secret is posted here directly by the owner's form (a settings page or a credential
card in chat) and stored encrypted; only its id goes into an integration or MCP
connection, and no agent, transcript or event ever sees the value. A news feed the owner
adds trusts its domain (the owner added it), so agents may subscribe more feeds there;
removing the last feed of a site removes that site from the trusted list too (it stays
restorable there), so an agent asks again before subscribing it.
"""

from typing import Any

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.agent_secrets import SecretCreate
from lonora_core.user_error import LonoraError
from lonora_db.integrations import IntegrationRepository, feed_host
from lonora_db.schema import IntegrationRow, ResourceRow
from lonora_db.trusted_sources import feed_trusted, revoke_feed_sites, trust_source
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime
from . import resource_router


class OwnerIntegrationRepository(IntegrationRepository):
    async def create(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        resource_id: str | None = None,
    ) -> ResourceRow:
        row = await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )
        if row.payload.get("type") == "news_feed":
            domain = feed_host(str(row.payload["url"]))
            if not await feed_trusted(session, owner_id, domain):
                await trust_source(session, owner_id, "feed_domain", domain, via="owner_ui")
        return row

    async def delete(self, session: AsyncSession, owner_id: str, resource_id: str) -> None:
        row = await self.get(session, owner_id, resource_id, lock=True)
        url = str(row.payload.get("url") or "") if row.payload.get("type") == "news_feed" else ""
        await super().delete(session, owner_id, resource_id)
        if not url:
            return
        others = await session.scalars(
            select(IntegrationRow).where(
                IntegrationRow.owner_id == owner_id, IntegrationRow.id != resource_id
            )
        )
        remaining: list[str] = []
        for other in others:
            if other.payload.get("type") == "news_feed":
                try:
                    remaining.append(feed_host(str(other.payload.get("url") or "")))
                except LonoraError:
                    continue
        try:
            host = feed_host(url)
        except LonoraError:
            return
        await revoke_feed_sites(session, owner_id, host, remaining)


router = resource_router("/integrations", OwnerIntegrationRepository())


@router.post("/secrets", status_code=201)
async def secret(
    request: Request, body: SecretCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, str]:
    secret_id = (
        await runtime(request)
        .services(owner.id)
        .secrets.write(body.name, body.value, "integration")
    )
    return {"id": secret_id}
