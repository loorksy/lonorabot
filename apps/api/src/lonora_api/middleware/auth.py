from typing import cast

from fastapi import Request
from lonora_auth.identity import OwnerIdentity
from lonora_auth.sessions import check_csrf, read_session
from lonora_db.personal_agent import ensure_personal_agent

from ..runtime import ApiRuntime


def runtime(request: Request) -> ApiRuntime:
    return cast(ApiRuntime, request.app.state.runtime)


async def require_owner(request: Request) -> OwnerIdentity:
    authorization = request.headers.get("authorization", "")
    bearer = authorization[7:] if authorization.lower().startswith("bearer ") else None
    token = bearer or request.cookies.get("lonora_session")
    async with runtime(request).db.sessions() as session, session.begin():
        identity = await read_session(session, token)
        if not bearer and request.method not in {"GET", "HEAD", "OPTIONS"}:
            await check_csrf(session, identity, request.headers.get("x-csrf-token"))
        await ensure_personal_agent(session, identity.id)
        return identity
