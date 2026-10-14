"""Actual python-socketio/engine.io/aiohttp and SDK reconnect code against a local server."""

import asyncio
import importlib
import socket
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from aiohttp import web
from lonora_adapters.brokers.metaapi import configure_sdk_transport

socketio: Any = importlib.import_module("socketio")
websocket_module: Any = importlib.import_module(
    "metaapi_cloud_sdk.clients.metaapi.metaapi_websocket_client"
)


def allow_local_server(url: str) -> str:
    return url


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def local_server() -> tuple[web.AppRunner, str]:
    server = socketio.AsyncServer(async_mode="aiohttp")
    app = web.Application()
    server.attach(app, socketio_path="ws")
    runner = web.AppRunner(app)
    await runner.setup()
    port = free_port()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    # A resolvable name keeps aiohttp's asynchronous DNS step, where the SDK race occurs.
    return runner, "http://localhost:" + str(port)


async def reconnect_after_disconnect(url: str) -> None:
    client = websocket_module.socketio.AsyncClient(reconnection=False)
    await client.connect(url, socketio_path="ws")
    sessions = {id(client.eio.http)}
    for _ in range(8):
        # MetaApiWebsocketClient._reconnect: disconnect, then connect again immediately.
        await client.disconnect()
        await asyncio.wait_for(client.connect(url, socketio_path="ws"), 10)
        assert client.connected
        sessions.add(id(client.eio.http))
    previous = client.eio.http
    await client.disconnect()
    await asyncio.sleep(0.05)
    assert previous.closed and len(sessions) == 9
    print("PASS each SDK socket connection uses its own HTTP session; immediate reconnects succeed")


async def forbidden_websocket_target() -> None:
    client = websocket_module.socketio.AsyncClient(reconnection=False)
    try:
        await client.connect("https://example.com", socketio_path="ws")
    except Exception as error:
        assert getattr(error, "code", None) == "broker_endpoint_forbidden"
    else:
        raise AssertionError("non-MetaApi socket endpoint accepted")
    print("PASS socket endpoint validation still applies to every connection")


class ScriptedSocket:
    def __init__(self, instance: dict[str, Any], failures: list[BaseException]):
        self.instance, self.failures = instance, failures
        self.connected = False
        self.attempts = 0

    async def disconnect(self) -> None:
        self.connected = False

    async def connect(self, url: str, **kwargs: Any) -> None:
        self.attempts += 1
        await asyncio.sleep(0)
        if self.failures:
            raise self.failures.pop(0)
        self.connected = True
        self.instance["connectResult"].set_result(None)

    async def wait(self) -> None:
        return None


def scripted_client(failures: list[BaseException]) -> tuple[Any, dict[str, Any], ScriptedSocket]:
    instance: dict[str, Any] = {
        "connected": True,
        "isReconnecting": False,
        "reconnectWaitTime": 0.001,
        "connectResult": None,
        "resolved": False,
        "sessionId": "",
    }
    sdk_socket = ScriptedSocket(instance, failures)
    instance["socket"] = sdk_socket
    reconnected: list[tuple[int, int, str]] = []

    async def server_url(*args: Any) -> str:
        return "https://mt-client-api-v1.london-a.agiliumtrade.ai"

    async def fire_reconnected(*args: Any) -> None:
        reconnected.append(args)

    client = SimpleNamespace(
        _socket_instances={"london": {0: [instance]}},
        _connect_timeout=5,
        _token="fixture-token",
        _get_server_url=server_url,
        _fire_reconnected=fire_reconnected,
        reconnected=reconnected,
    )
    return client, instance, sdk_socket


async def reconnect_survives_spurious_cancellation() -> None:
    reconnect = websocket_module.MetaApiWebsocketClient._reconnect
    client, instance, sdk_socket = scripted_client([asyncio.CancelledError()])
    # Socket.IO runs this from its disconnect handler and swallows CancelledError.
    await asyncio.wait_for(reconnect(client, 0, 0, "london"), 5)
    assert sdk_socket.attempts == 2 and sdk_socket.connected
    assert instance["isReconnecting"] is False and client.reconnected == [(0, 0, "london")]
    print("PASS SDK reconnect retries after a cancelled handshake instead of staying disconnected")

    client, instance, sdk_socket = scripted_client([])

    async def never_connects(url: str, **kwargs: Any) -> None:
        await asyncio.sleep(3600)

    sdk_socket.connect = never_connects
    task = asyncio.ensure_future(reconnect(client, 0, 0, "london"))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("owner cancellation was swallowed")
    print("PASS owner cancellation of a reconnect still propagates")


async def main() -> None:
    configure_sdk_transport()
    runner, url = await local_server()
    try:
        with patch("lonora_adapters.brokers.metaapi.validate_sdk_url", allow_local_server):
            await reconnect_after_disconnect(url)
        await forbidden_websocket_target()
        await reconnect_survives_spurious_cancellation()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
