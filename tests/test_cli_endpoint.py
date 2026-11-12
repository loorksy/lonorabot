"""The `lonora` CLI endpoint and client (mandate 7.3, step 1: identity and read commands).

Needs ``LONORA_DATABASE_URL`` (a disposable *_test database), like the other API tests.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

CLIENT = Path(__file__).resolve().parents[1] / "packages" / "cli" / "lonora"


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The CLI endpoint is exercised against a disposable database.")


def snapshot() -> dict[str, Any]:
    from datetime import timedelta

    from lonora_contracts.domain import utcnow

    return {
        "currency": "USD",
        "balance": "10000",
        "instruments": [
            {
                "symbol": "XAUUSDm",
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.01",
                "volume_max": "100",
                "volume_step": "0.01",
            }
        ],
        "quotes": {
            "XAUUSDm": {
                "symbol": "XAUUSDm",
                "bid": "2400.10",
                "ask": "2400.40",
                "observed_at": utcnow().isoformat(),
                "source": "cli-fixture",
            }
        },
        "candles": {
            "XAUUSDm:15m": [
                {
                    "symbol": "XAUUSDm",
                    "timeframe": "15m",
                    "time": (utcnow() - timedelta(minutes=15)).isoformat(),
                    "open": "2399",
                    "high": "2402",
                    "low": "2398",
                    "close": "2400",
                    "volume": "10",
                }
            ]
        },
    }


class Setup:
    async def open(self) -> "Setup":
        import httpx
        from check_streaming import Fixture
        from lonora_api.cli.app import create_cli_app

        self.fixture = await Fixture().open()
        self.connections: list[str] = []
        self.cli = httpx.AsyncClient(
            transport=httpx.ASGITransport(create_cli_app(self.fixture.runtime)),
            base_url="http://cli",
        )
        self.agent = (await self.fixture.agent("cli"))["id"]
        return self

    async def connect(self) -> str:
        connection = await self.fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
        await self.fixture.request(
            "POST", f"/trading/connections/{connection['id']}/simulation", {"snapshot": snapshot()}
        )
        self.connections.append(connection["id"])
        return connection["id"]

    async def token(self, agent_id: str | None = None) -> str:
        from lonora_db.cli_tokens import cli_token

        runtime = self.fixture.runtime
        async with runtime.db.sessions() as session, session.begin():
            return await cli_token(
                session,
                runtime.settings.encryption_key.get_secret_value(),
                self.fixture.owner,
                agent_id or self.agent,
            )

    async def call(self, command: str, token: str | None, **body: Any) -> tuple[int, Any]:
        headers = {"Authorization": "Bearer " + token} if token else {}
        response = await self.cli.post("/v1/" + command, json=body, headers=headers)
        assert response.status_code == 200, response.text
        answer = response.json()
        assert set(answer) == {"exit", "output"} and isinstance(answer["output"], dict)
        return answer["exit"], answer["output"]

    async def close(self) -> None:
        await self.cli.aclose()
        for connection in self.connections:
            await self.fixture.client.delete("/api/trading/connections/" + connection)
        await self.fixture.close()


@pytest.mark.asyncio
async def test_identity_is_refused_with_77_and_nothing_is_read() -> None:
    database()
    setup = await Setup().open()
    try:
        await setup.connect()
        for token in (None, "", "lnr_" + "x" * 43, "not-a-token", "lnr_" + "y" * 200):
            code, output = await setup.call("price", token, symbol="XAUUSDm")
            assert (code, output) == (77, {"error": "identity_refused"}), token
        # A token is refused before the command is even looked at.
        assert await setup.call("no_such_command", None) == (77, {"error": "identity_refused"})
    finally:
        await setup.close()


@pytest.mark.asyncio
async def test_one_token_per_agent_stable_and_revoked_with_the_agent() -> None:
    database()
    from lonora_db.cli_tokens import agent_for_cli_token, revoke_cli_token

    setup = await Setup().open()
    try:
        await setup.connect()
        token = await setup.token()
        assert token == await setup.token(), "issued once, the same value for every command"
        other = (await setup.fixture.agent("other"))["id"]
        other_token = await setup.token(other)
        assert other_token != token
        runtime = setup.fixture.runtime
        async with runtime.db.sessions() as session:
            assert (await agent_for_cli_token(session, token)).id == setup.agent  # type: ignore[union-attr]
            assert (await agent_for_cli_token(session, other_token)).id == other  # type: ignore[union-attr]
        # W-TEAM's delete calls the revoke function; the cascade covers a direct delete.
        async with runtime.db.sessions() as session, session.begin():
            await revoke_cli_token(session, other)
        assert (await setup.call("account", other_token))[0] == 77
        await setup.fixture.request("DELETE", "/agents/" + setup.agent)
        setup.fixture.agents.remove(setup.agent)
        assert (await setup.call("account", token))[0] == 77
    finally:
        await setup.close()


@pytest.mark.asyncio
async def test_read_commands_use_the_tool_services_with_broker_symbols() -> None:
    database()
    setup = await Setup().open()
    try:
        account = await setup.connect()
        token = await setup.token()
        code, output = await setup.call("price", token, symbol="XAUUSDm")
        assert code == 0, output
        assert output["account"] == account and output["symbol"] == "XAUUSDm"
        assert output["bid"] == "2400.10" and output["ask"] == "2400.40"
        code, output = await setup.call(
            "candles", token, symbol="XAUUSDm", timeframe="15m", count=1
        )
        assert code == 0, output
        assert [c["close"] for c in output["candles"]] == ["2400"]
        code, output = await setup.call("account", token)
        assert code == 0 and output["account"]["balance"] == "10000", output
        assert (await setup.call("positions", token)) == (0, {"account": account, "positions": []})
        assert (await setup.call("orders", token)) == (0, {"account": account, "orders": []})
        # The tool's own input contract bounds the request for both callers.
        code, output = await setup.call(
            "candles", token, symbol="XAUUSDm", timeframe="15m", count=5000
        )
        assert (code, output) == (20, {"error": "invalid_arguments"})
        assert (await setup.call("price", token, symbol="XAUUSDm", sl=1))[0] == 20
        assert (await setup.call("nope", token)) == (20, {"error": "unknown_command"})
    finally:
        await setup.close()


@pytest.mark.asyncio
async def test_account_is_required_when_several_are_connected() -> None:
    database()
    setup = await Setup().open()
    try:
        first = await setup.connect()
        second = await setup.connect()
        token = await setup.token()
        code, output = await setup.call("positions", token)
        assert (code, output["error"]) == (20, "account_required")
        code, output = await setup.call("positions", token, account=second)
        assert (code, output["account"]) == (0, second)
        code, output = await setup.call("price", token, symbol="XAUUSDm", account=first)
        assert (code, output["account"]) == (0, first)
        assert (await setup.call("positions", token, account=uuid4().hex))[0] == 20
    finally:
        await setup.close()


async def run_client(socket: Path, env: dict[str, str], *args: str) -> tuple[int, Any]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(CLIENT),
        *args,
        env={"PATH": os.environ.get("PATH", ""), "LONORA_CLI_SOCKET": str(socket), **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await process.communicate()
    lines = out.decode().splitlines()
    assert len(lines) == 1, out
    return process.returncode or 0, json.loads(lines[0])


@pytest.mark.asyncio
async def test_client_over_the_unix_socket_writes_one_json_object(tmp_path: Path) -> None:
    database()
    import uvicorn
    from lonora_api.cli.app import create_cli_app
    from lonora_api.server import cli_socket_path

    setup = await Setup().open()
    socket = tmp_path / "cli" / "lonora.sock"
    server = uvicorn.Server(
        uvicorn.Config(
            create_cli_app(setup.fixture.runtime),
            uds=cli_socket_path(socket),
            lifespan="off",
            log_level="warning",
        )
    )
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    serving = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(10):
            while not server.started:  # noqa: ASYNC110 - uvicorn exposes only a flag
                await asyncio.sleep(0.02)
        assert socket.stat().st_mode & 0o777 == 0o666, "every agent user may connect"
        account = await setup.connect()
        token = await setup.token()
        # No token: refused by the client itself, so nothing reaches the endpoint.
        assert await run_client(tmp_path / "absent.sock", {}, "price", "XAUUSDm") == (
            77,
            {"error": "identity_refused"},
        )
        assert (await run_client(socket, {"LONORA_AGENT_TOKEN": "lnr_wrong"}, "orders"))[0] == 77
        good = {"LONORA_AGENT_TOKEN": token}
        code, output = await run_client(socket, good, "price", "XAUUSDm")
        assert code == 0 and output["account"] == account and output["ask"] == "2400.40"
        code, output = await run_client(socket, good, "candles", "XAUUSDm", "15m", "1")
        assert code == 0 and len(output["candles"]) == 1
        code, output = await run_client(socket, good, "positions", "--account", account)
        assert (code, output) == (0, {"account": account, "positions": []})
        code, output = await run_client(socket, good, "candles", "XAUUSDm", "15m", "many")
        assert code == 20 and output["error"] == "invalid_arguments"
        code, output = await run_client(tmp_path / "absent.sock", good, "account")
        assert (code, output) == (20, {"error": "endpoint_unreachable"})
    finally:
        server.should_exit = True
        await serving
        await setup.close()


@pytest.mark.asyncio
async def test_only_full_scope_runs_receive_the_token() -> None:
    database()
    from lonora_db.schema import RunRow
    from lonora_tools.cli_token import token_for_command

    setup = await Setup().open()
    try:
        runtime = setup.fixture.runtime
        key = runtime.settings.encryption_key.get_secret_value()
        thread = (await setup.fixture.request("POST", "/threads", {"agent_id": setup.agent}))["id"]
        async with runtime.db.sessions() as session, session.begin():
            full = RunRow(thread_id=thread, agent_id=setup.agent, trigger="user")
            observe = RunRow(
                thread_id=thread,
                agent_id=setup.agent,
                trigger="broker_event",
                model_metadata={"authority": "observe_only"},
            )
            session.add_all([full, observe])
            await session.flush()
            helper = RunRow(
                thread_id=thread, agent_id=setup.agent, trigger="subagent", parent_run_id=full.id
            )
            session.add(helper)
            await session.flush()
            under_helper = RunRow(
                thread_id=thread, agent_id=setup.agent, trigger="user", parent_run_id=helper.id
            )
            session.add(under_helper)
            await session.flush()
            ids = full.id, observe.id, helper.id, under_helper.id
        async with runtime.db.sessions() as session, session.begin():
            tokens = [await token_for_command(session, key, run_id) for run_id in ids]
            assert await token_for_command(session, key, uuid4().hex) is None
        assert tokens[0] == await setup.token()
        assert tokens[1:] == [None, None, None]
    finally:
        await setup.close()
