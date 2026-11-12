"""The workspace network guard: runs as root with NET_ADMIN in the container whose network
namespace the workspace shares (7.1.4).

It installs the egress rules (egress.py), points the shared resolver configuration at its
own forwarder on 127.0.0.1:53, refuses names under a broker domain or Lonora's domain,
and every few minutes resolves the known MetaApi hosts and Lonora's domain itself so a
program that dials those addresses directly is refused too.
"""

import argparse
import asyncio
import contextlib
import logging
import os
import socket
import struct
import subprocess
import sys
from pathlib import Path

from lonora_core.broker_endpoints import METAAPI_KNOWN_HOSTS

from . import dns
from .egress import DOCKER_RESOLVER, TABLE, denied_domains, name_denied, networks, ruleset

READY = Path("/run/lonora-netguard.ready")
RESOLV = Path("/etc/resolv.conf")
LISTEN = ("127.0.0.1", 53)
UPSTREAM = (DOCKER_RESOLVER, 53)
log = logging.getLogger("lonora.workspace.netguard")


def apply(extra: list[str]) -> None:
    subprocess.run(["nft", "-f", "-"], input=ruleset(extra).encode(), check=True, timeout=20)


async def resolve(names: list[str]) -> list[str]:
    """Every A and AAAA address of `names`, asked of Docker's resolver all at once."""

    async def one(name: str, kind: int) -> list[str]:
        try:
            return dns.addresses(await forward_udp(dns.query(name, kind)))
        except (TimeoutError, OSError, dns.DnsError):
            return []

    found = await asyncio.gather(*(one(n, k) for n in names for k in (dns.A, dns.AAAA)))
    return [address for addresses in found for address in addresses]


async def forward_udp(packet: bytes) -> bytes:
    loop = asyncio.get_running_loop()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        await loop.sock_sendto(sock, packet, UPSTREAM)
        answer, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 65535), 5)
        return answer


async def forward_tcp(packet: bytes) -> bytes:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(*UPSTREAM), 5)
    try:
        writer.write(struct.pack("!H", len(packet)) + packet)
        await writer.drain()
        size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), 5))[0]
        return await asyncio.wait_for(reader.readexactly(size), 5)
    finally:
        writer.close()


def verdict(packet: bytes, domains: tuple[str, ...]) -> bytes | None:
    """A refusal to send back, or None when the query may be forwarded."""
    try:
        name, _ = dns.question(packet)
    except dns.DnsError:
        return dns.reply(packet, dns.FORMERR)
    if name_denied(name, domains):
        return dns.reply(packet, dns.NXDOMAIN)
    return None


class Udp(asyncio.DatagramProtocol):
    def __init__(self, domains: tuple[str, ...]) -> None:
        self.domains = domains
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str | int, int]) -> None:
        asyncio.get_running_loop().create_task(self.answer(data, addr))

    async def answer(self, data: bytes, addr: tuple[str | int, int]) -> None:
        refusal = verdict(data, self.domains)
        try:
            response = refusal if refusal is not None else await forward_udp(data)
        except (TimeoutError, OSError):
            return
        if self.transport is not None:
            self.transport.sendto(response, addr)


def announce() -> None:
    """Point the shared resolver configuration at the forwarder, then report ready."""
    RESOLV.write_text("nameserver 127.0.0.1\noptions ndots:0 timeout:2 attempts:2\n")
    READY.write_text("ready\n")


async def serve(domains: tuple[str, ...], extra: list[str], refresh_seconds: int) -> None:
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(lambda: Udp(domains), local_addr=LISTEN)

    async def tcp(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), 10))[0]
            packet = await asyncio.wait_for(reader.readexactly(size), 10)
            refusal = verdict(packet, domains)
            response = refusal if refusal is not None else await forward_tcp(packet)
            writer.write(struct.pack("!H", len(response)) + response)
            await writer.drain()
        except (TimeoutError, OSError, asyncio.IncompleteReadError, struct.error):
            pass
        finally:
            writer.close()

    await asyncio.start_server(tcp, *LISTEN)
    announce()
    log.warning("workspace_netguard_ready domains=%d", len(domains))
    known = [*METAAPI_KNOWN_HOSTS, *domains]
    while True:
        await asyncio.sleep(refresh_seconds)
        try:
            apply(extra + await resolve(known))
        except (subprocess.SubprocessError, OSError) as error:
            log.warning("workspace_netguard_refresh_failed type=%s", type(error).__name__)


def check() -> int:
    """Health: the table is installed and the forwarder answers."""
    listed = subprocess.run(["nft", "list", "table", "inet", TABLE], capture_output=True)
    if listed.returncode != 0 or not READY.exists():
        return 1
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        probe = dns.query("probe.agiliumtrade.ai", dns.A)
        try:
            sock.sendto(probe, LISTEN)
            answer = sock.recv(512)
        except OSError:
            return 1
    return 0 if answer[:2] == probe[:2] and answer[3] & 0x0F == dns.NXDOMAIN else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        sys.exit(check())
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    READY.unlink(missing_ok=True)
    domains = denied_domains(
        os.environ.get("LONORA_DOMAIN"),
        os.environ.get("LONORA_WORKSPACE_BLOCKED_DOMAINS", "").split(),
    )
    extra = os.environ.get("LONORA_WORKSPACE_BLOCKED_ADDRESSES", "").split()
    networks(extra)  # refuse a malformed address before anything is installed
    refresh = int(os.environ.get("LONORA_WORKSPACE_GUARD_REFRESH_SECONDS", "300"))
    apply(extra)

    async def run() -> None:
        resolved = await resolve([*METAAPI_KNOWN_HOSTS, *domains])
        apply(extra + resolved)
        await serve(domains, extra, refresh)

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
