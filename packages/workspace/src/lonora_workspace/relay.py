"""The workspace's connection relay (7.1.4): every agent TCP connection leaving the host
is redirected here by the guard's nftables rules.

A connection whose client speaks first must be TLS, HTTP or SSH; anything else (SOCKS,
h2c, raw tunnels) is refused. For TLS and HTTP the relay reads the name the client asks
for (the ClientHello's server name, the Host header, a proxy's CONNECT target or absolute
URI), refuses names under a denied domain (MetaApi, Lonora's own), and requires the
address being dialled to be one that name resolves to: a hard-coded MetaApi address
behind an innocent name, or a public proxy, does not pass. A connection whose server
speaks first (SMTP, databases) passes once the server has spoken. Accepted connections
go to the original destination from the guard as root, still under its address rules.

What it cannot see: an encrypted tunnel the agent builds itself over SSH, and a CDN that
serves MetaApi and other names on the same addresses (domain fronting). The MetaApi token
never being in the workspace (7.2.3) is what holds there.
"""

import asyncio
import contextlib
import ipaddress
import logging
import socket
import struct
from collections.abc import Awaitable, Callable
from pathlib import Path

from .egress import name_denied

SO_ORIGINAL_DST = 80
PEEK_BYTES = 16384
PEEK_SECONDS = 10
IDLE_SECONDS = 3600
PER_USER = 256
# A server that speaks first (SSH banners, SMTP, databases) gets the connection after this.
FIRST_BYTES_SECONDS = 1.5
HTTP_METHODS = (
    b"GET ",
    b"POST ",
    b"PUT ",
    b"HEAD ",
    b"DELETE ",
    b"PATCH ",
    b"OPTIONS ",
    b"CONNECT ",
)
ECH_EXTENSION = 0xFE0D
log = logging.getLogger("lonora.workspace.relay")


class Refused(ValueError):
    pass


def tls_server_name(hello: bytes) -> str | None:
    """The server name of a TLS ClientHello, None when it is incomplete (read more).
    Raises Refused for anything that is not a plain hello naming one host."""
    if len(hello) < 5:
        return None
    if hello[0] != 0x16:
        raise Refused("relay_not_tls")
    record = struct.unpack("!H", hello[3:5])[0]
    if len(hello) < 5 + record:
        return None
    body = hello[5 : 5 + record]
    if len(body) < 4 or body[0] != 0x01:
        raise Refused("relay_not_client_hello")
    size = int.from_bytes(body[1:4], "big")
    if size > len(body) - 4:
        # A hello split over several records: refuse rather than reassemble.
        raise Refused("relay_hello_fragmented")
    message = body[4 : 4 + size]
    try:
        offset = 2 + 32
        offset += 1 + message[offset]  # session id
        suites = struct.unpack("!H", message[offset : offset + 2])[0]
        offset += 2 + suites
        offset += 1 + message[offset]  # compression methods
        end = offset + 2 + struct.unpack("!H", message[offset : offset + 2])[0]
        offset += 2
        name: str | None = None
        while offset + 4 <= end:
            kind, length = struct.unpack("!HH", message[offset : offset + 4])
            data = message[offset + 4 : offset + 4 + length]
            if kind == ECH_EXTENSION:
                raise Refused("relay_encrypted_hello")
            if kind == 0:
                # server_name_list: one host_name entry.
                listed = struct.unpack("!H", data[0:2])[0]
                entries = data[2 : 2 + listed]
                names: list[str] = []
                position = 0
                while position + 3 <= len(entries):
                    entry_type = entries[position]
                    entry_size = struct.unpack("!H", entries[position + 1 : position + 3])[0]
                    value = entries[position + 3 : position + 3 + entry_size]
                    if entry_type == 0:
                        names.append(value.decode("ascii", "replace").lower())
                    position += 3 + entry_size
                if len(names) != 1:
                    raise Refused("relay_server_name_invalid")
                name = names[0]
            offset += 4 + length
    except (IndexError, struct.error):
        raise Refused("relay_hello_invalid") from None
    if not name:
        raise Refused("relay_no_server_name")
    return name


def http_host(request: bytes) -> str | None:
    """The host an HTTP/1 request names (a proxy's CONNECT target, else the Host header),
    None when the headers are not complete yet."""
    end = request.find(b"\r\n\r\n")
    if end < 0:
        if len(request) >= PEEK_BYTES:
            raise Refused("relay_headers_too_long")
        return None
    lines = request[:end].split(b"\r\n")
    parts = lines[0].split(b" ")
    if parts[0] == b"CONNECT" and len(parts) >= 2:
        return strip_port(parts[1].decode("ascii", "replace").lower())
    if len(parts) >= 2 and b"://" in parts[1]:
        # An absolute URI: the request is for a proxy; its host is the target.
        target = parts[1].split(b"://", 1)[1].split(b"/", 1)[0]
        return strip_port(target.decode("ascii", "replace").lower())
    hosts = [
        line.split(b":", 1)[1].strip().decode("ascii", "replace").lower()
        for line in lines[1:]
        if line.lower().startswith(b"host:")
    ]
    if len(hosts) != 1 or not hosts[0]:
        raise Refused("relay_no_host")
    return strip_port(hosts[0])


def strip_port(host: str) -> str:
    if host.startswith("["):
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def kind(first: bytes) -> str:
    """'tls', 'http', 'ssh', or '' while too few bytes have arrived to tell.
    Any other client-first protocol is refused."""
    if first[:1] == b"\x16":
        return "tls"
    if any(first.startswith(method) for method in HTTP_METHODS):
        return "http"
    if first.startswith(b"SSH-"):
        return "ssh"
    prefixes = (*HTTP_METHODS, b"SSH-")
    if len(first) < 8 and any(prefix.startswith(first) for prefix in prefixes):
        return ""
    raise Refused("relay_protocol_refused")


def requested_name(first: bytes) -> str | None:
    """The name the connection asks for; '' for SSH, which names nothing; None until
    enough bytes have arrived."""
    found = kind(first)
    if found == "tls":
        return tls_server_name(first)
    if found == "http":
        return http_host(first)
    return "" if found == "ssh" else None


def peer_uid(host: str, port: int) -> int | None:
    """The uid owning the client end of a connection to the relay (same namespace)."""
    wanted = f"{socket.inet_aton(host)[::-1].hex().upper()}:{port:04X}"
    with contextlib.suppress(OSError):
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1] == wanted:
                return int(fields[7])
    return None


def original_destination(sock: socket.socket) -> tuple[str, int]:
    raw = sock.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
    port = struct.unpack("!H", raw[2:4])[0]
    return socket.inet_ntoa(raw[4:8]), port


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await asyncio.wait_for(reader.read(65536), IDLE_SECONDS):
            writer.write(data)
            await writer.drain()
    except (OSError, asyncio.IncompleteReadError, TimeoutError):
        pass
    finally:
        with contextlib.suppress(OSError):
            writer.close()


Resolver = Callable[[str], Awaitable[set[str]]]


class Relay:
    def __init__(self, domains: tuple[str, ...], resolve: Resolver, limit: int = 2048):
        self.domains = domains
        self.resolve = resolve
        self.slots = asyncio.Semaphore(limit)
        self.users: dict[int, int] = {}

    async def bound(self, name: str, address: str) -> None:
        """The dialled address must be the name itself or one of its addresses."""
        if name_denied(name, self.domains):
            raise Refused("relay_name_denied")
        with contextlib.suppress(ValueError):
            if ipaddress.ip_address(name) == ipaddress.ip_address(address):
                return
            raise Refused("relay_address_mismatch")
        if address not in await self.resolve(name):
            raise Refused("relay_address_mismatch")

    async def inspect(self, reader: asyncio.StreamReader, first: bytes, address: str) -> bytes:
        """Read until the client's request names its target, then check it."""
        async with asyncio.timeout(PEEK_SECONDS):
            while (name := requested_name(first)) is None:
                chunk = await reader.read(PEEK_BYTES)
                if not chunk:
                    raise Refused("relay_closed_early")
                first += chunk
                if len(first) > PEEK_BYTES * 4:
                    raise Refused("relay_hello_too_long")
        if name:
            await self.bound(name, address)
        return first

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client = writer.get_extra_info("peername")
        uid = peer_uid(client[0], client[1]) if client else None
        key = -1 if uid is None else uid
        if self.slots.locked() or self.users.get(key, 0) >= PER_USER:
            writer.close()
            return
        self.users[key] = self.users.get(key, 0) + 1
        upstream: asyncio.StreamWriter | None = None
        try:
            async with self.slots:
                host, port = original_destination(writer.get_extra_info("socket"))
                first = b""
                with contextlib.suppress(TimeoutError):
                    first = await asyncio.wait_for(reader.read(PEEK_BYTES), FIRST_BYTES_SECONDS)
                    if not first:
                        return
                if first:
                    first = await self.inspect(reader, first, host)
                    up_reader, upstream = await asyncio.wait_for(
                        asyncio.open_connection(host, port), 15
                    )
                    upstream.write(first)
                    await upstream.drain()
                else:
                    # Quiet client: whoever speaks first decides. Only a server that
                    # speaks first passes uninspected; a client is checked as above.
                    up_reader, upstream = await asyncio.wait_for(
                        asyncio.open_connection(host, port), 15
                    )
                    from_client = asyncio.ensure_future(reader.read(PEEK_BYTES))
                    from_server = asyncio.ensure_future(up_reader.read(65536))
                    done, _ = await asyncio.wait(
                        {from_client, from_server},
                        timeout=PEEK_SECONDS * 6,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if from_client in done:
                        from_server.cancel()
                        first = from_client.result()
                        if not first:
                            return
                        first = await self.inspect(reader, first, host)
                        upstream.write(first)
                        await upstream.drain()
                    elif from_server in done:
                        from_client.cancel()
                        greeting = from_server.result()
                        if not greeting:
                            return
                        writer.write(greeting)
                        await writer.drain()
                    else:
                        from_client.cancel()
                        from_server.cancel()
                        return
                await asyncio.gather(pipe(reader, upstream), pipe(up_reader, writer))
        except Refused as refusal:
            log.warning("workspace_relay_refused reason=%s uid=%s", refusal, uid)
        except (OSError, TimeoutError):
            pass
        finally:
            self.users[key] -= 1
            for stream in (writer, upstream):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()

    async def serve(self, port: int) -> None:
        await asyncio.start_server(self.handle, "127.0.0.1", port, backlog=512)
