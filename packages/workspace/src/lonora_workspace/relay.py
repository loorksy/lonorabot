"""The workspace's connection relay (7.1.4): every agent TCP connection leaving the host
is redirected here by the guard's nftables rules. The relay reads what the program asks
for in its first bytes: the TLS ClientHello's server name, an HTTP Host header, or an HTTP
proxy's CONNECT target. It refuses any name under a denied domain (MetaApi, Lonora's
own), a TLS hello with no server name or with Encrypted Client Hello, and an HTTP request
with no host. A protocol it does not recognise (SSH, databases, servers that speak
first) passes through. Accepted connections go to the original destination from the
guard as root, still under the guard's address rules, and bytes are copied both ways.

So a hard-coded MetaApi address, DNS-over-HTTPS or a public HTTP proxy does not reach
MetaApi: the name a MetaApi endpoint needs is itself refused. An encrypted tunnel the
agent builds itself (SSH -D, a VPN) is not visible to it; the MetaApi token never being
in the workspace (7.2.3) is what holds there.
"""

import asyncio
import contextlib
import logging
import socket
import struct

from .egress import name_denied

SO_ORIGINAL_DST = 80
PEEK_BYTES = 16384
PEEK_SECONDS = 10
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
    """'tls', 'http', 'unknown', or '' while too few bytes have arrived to tell."""
    if first[:1] == b"\x16":
        return "tls"
    if any(first.startswith(method) for method in HTTP_METHODS):
        return "http"
    if len(first) < 8 and any(method.startswith(first) for method in HTTP_METHODS):
        return ""
    return "unknown"


def requested_name(first: bytes) -> str | None:
    """The name the connection asks for; '' for a protocol the relay passes through;
    None until enough bytes have arrived."""
    found = kind(first)
    if found == "tls":
        return tls_server_name(first)
    if found == "http":
        return http_host(first)
    return "" if found else None


def original_destination(sock: socket.socket) -> tuple[str, int]:
    raw = sock.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
    port = struct.unpack("!H", raw[2:4])[0]
    return socket.inet_ntoa(raw[4:8]), port


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (OSError, asyncio.IncompleteReadError):
        pass
    finally:
        with contextlib.suppress(OSError):
            writer.close()


class Relay:
    def __init__(self, domains: tuple[str, ...], limit: int = 512):
        self.domains = domains
        self.slots = asyncio.Semaphore(limit)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.slots.locked():
            writer.close()
            return
        async with self.slots:
            upstream: asyncio.StreamWriter | None = None
            try:
                sock = writer.get_extra_info("socket")
                host, port = original_destination(sock)
                first = b""
                name: str | None = None
                try:
                    first = await asyncio.wait_for(reader.read(PEEK_BYTES), FIRST_BYTES_SECONDS)
                    if not first:
                        return
                except TimeoutError:
                    name = ""  # the server speaks first
                async with asyncio.timeout(PEEK_SECONDS):
                    while name is None:
                        name = requested_name(first)
                        if name is None:
                            chunk = await reader.read(PEEK_BYTES)
                            if not chunk:
                                return
                            first += chunk
                            if len(first) > PEEK_BYTES * 4:
                                raise Refused("relay_hello_too_long")
                if name and name_denied(name, self.domains):
                    raise Refused("relay_name_denied")
                up_reader, upstream = await asyncio.wait_for(
                    asyncio.open_connection(host, port), 15
                )
                if first:
                    upstream.write(first)
                    await upstream.drain()
                await asyncio.gather(pipe(reader, upstream), pipe(up_reader, writer))
            except Refused as refusal:
                log.warning("workspace_relay_refused reason=%s", refusal)
            except (OSError, TimeoutError):
                pass
            finally:
                for stream in (writer, upstream):
                    if stream is not None:
                        with contextlib.suppress(OSError):
                            stream.close()

    async def serve(self, port: int) -> None:
        await asyncio.start_server(self.handle, "127.0.0.1", port, backlog=256)
