"""Check browser/native sessions and atomic conversations against a disposable PostgreSQL DB."""

import asyncio
import os
from typing import Any
from uuid import uuid4

import httpx
from lonora_api.app import create_app
from lonora_api.env import get_settings
from lonora_auth.sessions import token_hash
from lonora_db.schema import SessionRow, ThreadRow
from sqlalchemy import func, select
from sqlalchemy.engine import make_url


async def main() -> None:
    explicit_url = os.environ.get("LONORA_DATABASE_URL")
    try:
        url = make_url(explicit_url or "")
        safe = (
            url.drivername.startswith("postgresql")
            and (url.database or "").endswith(("_ci", "_test", "_verify"))
            and not {"database", "dbname"}.intersection(key.lower() for key in url.query)
        )
    except Exception:
        safe = False
    if not explicit_url or not safe:
        raise SystemExit(
            "Set LONORA_DATABASE_URL explicitly to a PostgreSQL *_ci, *_test or *_verify DB."
        )
    settings = get_settings()
    app, peer_app = create_app(settings), create_app(settings)
    runtime, peer_runtime = app.state.runtime, peer_app.state.runtime
    credentials = {
        "email": os.environ.get("LONORA_UI_TEST_EMAIL", "ci@example.com"),
        "password": os.environ.get("LONORA_UI_TEST_PASSWORD", "ci-only-owner-password"),
    }
    checks: list[str] = []
    agents: list[str] = []

    def check(name: str, condition: bool) -> None:
        assert condition, name
        checks.append(name)
        print("PASS", name, flush=True)

    async def request(
        client: httpx.AsyncClient,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        status: int = 200,
    ) -> dict[str, Any]:
        response = await client.request(method, "/api" + path, json=body)
        assert response.status_code == status, (
            f"{method} {path}: unexpected HTTP {response.status_code}"
        )
        return response.json()

    try:
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="https://lonora.test"
            ) as browser,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="https://lonora.test"
            ) as native,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(peer_app), base_url="https://lonora.test"
            ) as peer,
        ):
            try:
                status = await request(browser, "GET", "/onboarding")
                if not status["owner_initialized"]:
                    await request(
                        browser,
                        "POST",
                        "/onboarding",
                        {
                            **credentials,
                            "bootstrap_token": settings.bootstrap_token.get_secret_value(),
                        },
                        201,
                    )
                login = await request(browser, "POST", "/auth/login", credentials)
                browser.headers["X-CSRF-Token"] = login["csrf"]
                cookie = next(
                    (item for item in browser.cookies.jar if item.name == "lonora_session"), None
                )
                check(
                    "browser login creates its existing HttpOnly session",
                    cookie is not None and cookie.has_nonstandard_attr("HttpOnly"),
                )
                response = await native.post("/api/auth/mobile/login", json=credentials)
                assert response.status_code == 200, "native login failed"
                mobile: dict[str, Any] = response.json()
                token: str = mobile["token"]
                check(
                    "native login returns owner and opaque configured-lifetime token",
                    set(mobile) == {"owner", "token", "expires_in"}
                    and mobile["owner"] == login["owner"]
                    and len(token) >= 64
                    and mobile["expires_in"] == settings.session_seconds,
                )
                check(
                    "native login sets no cookies and prevents response caching",
                    not native.cookies
                    and "set-cookie" not in response.headers
                    and response.headers.get("cache-control") == "no-store",
                )
                async with runtime.db.sessions() as session:
                    durable = await session.get(SessionRow, token_hash(token))
                    check(
                        "durable session stores a token hash rather than its secret",
                        durable is not None
                        and durable.token_hash != token
                        and durable.owner_id == login["owner"]["id"],
                    )
                native.headers["Authorization"] = peer.headers["Authorization"] = "Bearer " + token
                identity = await request(peer, "GET", "/auth/session")
                check("native bearer survives a separate API runtime", identity == login["owner"])
                agent = await request(
                    browser,
                    "POST",
                    "/agents",
                    {"name": "Client regression " + uuid4().hex[:12]},
                    201,
                )
                agent_id: str = agent["id"]
                agents.append(agent_id)
                path = "/agents/" + agent_id + "/conversation"
                csrf = browser.headers.pop("X-CSRF-Token")
                denied = await request(browser, "POST", path, status=403)
                browser.headers["X-CSRF-Token"] = csrf
                check(
                    "cookie conversation mutation enforces CSRF", denied["code"] == "csrf_required"
                )
                async with runtime.db.sessions() as session:
                    count = await session.scalar(
                        select(func.count())
                        .select_from(ThreadRow)
                        .where(ThreadRow.agent_id == agent_id)
                    )
                check("rejected CSRF does not create a conversation", count == 0)
                replies = await asyncio.gather(
                    *(request(native if index % 2 else peer, "POST", path) for index in range(10))
                )
                identifiers = {reply["id"] for reply in replies}
                async with runtime.db.sessions() as session:
                    count = await session.scalar(
                        select(func.count())
                        .select_from(ThreadRow)
                        .where(
                            ThreadRow.owner_id == login["owner"]["id"],
                            ThreadRow.agent_id == agent_id,
                            ThreadRow.group_id.is_(None),
                        )
                    )
                check(
                    "10 concurrent cross-runtime clients create one durable direct conversation",
                    len(identifiers) == 1 and count == 1,
                )
                canonical_id = replies[0]["id"]
                current = await request(browser, "POST", path)
                check(
                    "browser and native clients share the same continuous conversation",
                    current["id"] == canonical_id,
                )
                manual = await request(
                    browser,
                    "POST",
                    "/threads",
                    {"agent_id": agent_id, "title": "Preserved manual history"},
                    201,
                )
                current = await request(peer, "POST", path)
                history = await request(browser, "GET", "/threads/" + manual["id"])
                check(
                    "manual historical threads remain available and canonical thread stays stable",
                    manual["id"] != canonical_id
                    and history["title"] == "Preserved manual history"
                    and current["id"] == canonical_id,
                )
                await request(native, "POST", "/auth/logout", {})
                await request(native, "GET", "/auth/session", status=401)
                await request(peer, "GET", "/auth/session", status=401)
                current_owner = await request(browser, "GET", "/auth/session")
                check(
                    "native logout revokes its durable session without revoking the browser",
                    current_owner == login["owner"],
                )
            finally:
                for agent_id in agents:
                    await request(browser, "DELETE", "/agents/" + agent_id)
                if browser.cookies.get("lonora_session") and browser.headers.get("X-CSRF-Token"):
                    await request(browser, "POST", "/auth/logout", {})
    finally:
        await runtime.close()
        await peer_runtime.close()
    print("Client integration checks passed:", len(checks))


if __name__ == "__main__":
    asyncio.run(main())
