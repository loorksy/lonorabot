"""The owner's Capabilities view: everything agents can use now, with source, state, last
use and Undo (``lonora_tools.capabilities``). Owner session only; it changes nothing.
Undo goes to the existing owner routes: removing a trusted source, revoking a Skill
version, deleting an integration or a saved MCP server."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_tools.capabilities import Infrastructure, capability_report

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/capabilities")


@router.get("")
async def capabilities(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    settings = rt.settings
    infrastructure = Infrastructure(
        searxng=bool(settings.searxng_url),
        browser=bool(settings.browser_url),
        # The production stack always runs the owner's workspace; the API cannot reach it
        # (only the Gateway does), so this reports the deployment, not a live check.
        workspace=True,
        chart_renderer=bool(settings.chart_renderer_url),
        mcp_declarations=settings.mcp_declarations,
        mcp_owner_trust=settings.mcp_owner_trust,
    )
    return await capability_report(rt.db, owner.id, infrastructure, for_agent=False)
