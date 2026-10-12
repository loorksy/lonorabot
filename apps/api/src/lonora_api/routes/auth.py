from fastapi import APIRouter, Depends, Request, Response
from lonora_auth.account_security import DUMMY_HASH, normalize_email, verify_password
from lonora_auth.identity import OwnerIdentity
from lonora_auth.sessions import issue_session, revoke
from lonora_contracts.auth import LoginRequest
from lonora_core.user_error import LonoraError
from lonora_db.owner import get_owner
from lonora_db.schema import OwnerRow

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/auth")


async def login_session(request: Request, body: LoginRequest) -> tuple[OwnerRow, str, str]:
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        owner = await get_owner(session)
        valid = verify_password(body.password, owner.password_hash if owner else DUMMY_HASH)
        if owner is None or owner.email != normalize_email(body.email) or not valid:
            raise LonoraError("unauthorized", 401)
        token, csrf = await issue_session(session, owner, rt.settings.session_seconds)
    return owner, token, csrf


@router.post("/login")
async def login(request: Request, response: Response, body: LoginRequest) -> dict[str, object]:
    rt = runtime(request)
    owner, token, csrf = await login_session(request, body)
    response.set_cookie(
        "lonora_session",
        token,
        httponly=True,
        secure=rt.settings.cookie_secure,
        samesite="strict",
        max_age=rt.settings.session_seconds,
    )
    response.set_cookie(
        "lonora_csrf",
        csrf,
        httponly=False,
        secure=rt.settings.cookie_secure,
        samesite="strict",
        max_age=rt.settings.session_seconds,
    )
    return {"owner": {"id": owner.id, "email": owner.email}, "csrf": csrf}


@router.post("/mobile/login")
async def mobile_login(
    request: Request, response: Response, body: LoginRequest
) -> dict[str, object]:
    owner, token, _ = await login_session(request, body)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {
        "owner": {"id": owner.id, "email": owner.email},
        "token": token,
        "expires_in": runtime(request).settings.session_seconds,
    }


@router.get("/session")
async def current(owner: OwnerIdentity = Depends(require_owner)) -> dict[str, str]:
    return {"id": owner.id, "email": owner.email}


@router.post("/logout")
async def logout(
    request: Request, response: Response, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        await revoke(session, owner)
    response.delete_cookie("lonora_session")
    response.delete_cookie("lonora_csrf")
    return {"logged_out": True}
