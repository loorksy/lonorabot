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
import time
from collections import OrderedDict
from pathlib import Path

from lonora_core.broker_endpoints import METAAPI_KNOWN_HOSTS

from . import dns
from .egress import (
    DOCKER_RESOLVER,
    RELAY_PORT,
    TABLE,
    denied_domains,
    name_denied,
    networks,
    ruleset,
)
from .relay import Relay

READY = Path("/run/lonora-netguard.ready")
RESOLV = Path("/etc/resolv.conf")
LISTEN = ("127.0.0.1", 53)
UPSTREAM = (DOCKER_RESOLVER, 53)
IN_FLIGHT = 128
# Addresses of a chain into a denied domain stay blocked this long (the most kept).
DENIED_SECONDS = 86400
DENIED_LIMIT = 4096
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
    """Ask Docker's resolver on a connected socket; only its reply to this very query
    counts, so no other local process can inject an answer."""
    loop = asyncio.get_running_loop()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        await loop.sock_connect(sock, UPSTREAM)
        await loop.sock_sendall(sock, packet)
        async with asyncio.timeout(5):
            while True:
                answer = await loop.sock_recv(sock, 65535)
                if dns.answers(packet, answer):
                    return answer


async def forward_tcp(packet: bytes) -> bytes:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(*UPSTREAM), 5)
    try:
        writer.write(struct.pack("!H", len(packet)) + packet)
        await writer.drain()
        size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), 5))[0]
        answer = await asyncio.wait_for(reader.readexactly(size), 5)
    finally:
        writer.close()
    if not dns.answers(packet, answer):
        raise OSError("dns_answer_mismatch")
    return answer


def verdict(packet: bytes, domains: tuple[str, ...]) -> bytes | None:
    """A refusal to send back, or None when the query may be forwarded."""
    try:
        name, _ = dns.question(packet)
    except dns.DnsError:
        return dns.reply(packet, dns.FORMERR)
    if name_denied(name, domains):
        return dns.reply(packet, dns.NXDOMAIN)
    return None


class Answers:
    """The addresses the forwarder recently gave out per name, so the relay can check
    that a connection goes where its name points (a CDN may rotate its answers). A chain
    that leads into a denied domain gives nothing, and its addresses are blocked."""

    LIMIT: int = 20000

    def __init__(self, domains: tuple[str, ...] = (), seconds: float = 900) -> None:
        self.domains = domains
        self.seconds = seconds
        self.names: OrderedDict[str, tuple[float, set[str]]] = OrderedDict()
        self.denied: OrderedDict[str, float] = OrderedDict()
        self.changed = asyncio.Event()

    def record(self, query: bytes, answer: bytes) -> None:
        with contextlib.suppress(dns.DnsError):
            name, _ = dns.question(query)
            if any(name_denied(n, self.domains) for n in dns.names(answer)):
                return
            found = set(dns.addresses(answer))
            if found:
                _, old = self.names.pop(name, (0.0, set()))
                self.names[name] = (time.monotonic() + self.seconds, old | found)
                while len(self.names) > self.LIMIT:
                    self.names.popitem(last=False)

    async def lookup(self, name: str) -> set[str]:
        found: set[str] = set()
        for kind in (dns.A, dns.AAAA):
            try:
                answer = await forward_udp(dns.query(name, kind))
                if any(name_denied(n, self.domains) for n in dns.names(answer)):
                    # Block only the addresses a denied name itself owns; a shared
                    # address named by something else stays reachable.
                    owned = {
                        address
                        for owner, address in dns.owned_addresses(answer)
                        if name_denied(owner, self.domains)
                    }
                    if owned - set(self.denied):
                        until = time.monotonic() + DENIED_SECONDS
                        for address in owned:
                            self.denied[address] = until
                        while len(self.denied) > DENIED_LIMIT:
                            self.denied.popitem(last=False)
                        self.changed.set()
                    return set()
                found |= set(dns.addresses(answer))
            except (TimeoutError, OSError, dns.DnsError):
                continue
        return found

    def blocked(self) -> set[str]:
        now = time.monotonic()
        return {address for address, until in self.denied.items() if until > now}

    async def of(self, name: str) -> set[str]:
        key = name.lower().rstrip(".")
        if name_denied(key, self.domains):
            return set()
        expiry, cached = self.names.get(key, (0.0, set()))
        fresh = await self.lookup(key)
        return fresh | (cached if expiry > time.monotonic() else set())


ANSWERS = Answers()


def screened(query: bytes, answer: bytes, domains: tuple[str, ...]) -> bytes:
    """The answer, unless it leads into a denied domain (a CNAME into MetaApi, say)."""
    try:
        if any(name_denied(name, domains) for name in dns.names(answer)):
            return dns.reply(query, dns.NXDOMAIN)
    except dns.DnsError:
        return dns.reply(query, dns.FORMERR)
    return answer


class Udp(asyncio.DatagramProtocol):
    def __init__(self, domains: tuple[str, ...]) -> None:
        self.domains = domains
        self.transport: asyncio.DatagramTransport | None = None
        self.pending: set[asyncio.Task[None]] = set()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str | int, int]) -> None:
        if len(self.pending) >= IN_FLIGHT:
            return  # a flood is dropped; the guard and other lookups keep working
        task = asyncio.get_running_loop().create_task(self.answer(data, addr))
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)

    async def answer(self, data: bytes, addr: tuple[str | int, int]) -> None:
        refusal = verdict(data, self.domains)
        try:
            if refusal is not None:
                response = refusal
            else:
                response = screened(data, await forward_udp(data), self.domains)
                ANSWERS.record(data, response)
        except (TimeoutError, OSError):
            return
        if self.transport is not None:
            self.transport.sendto(response, addr)


def announce() -> None:
    """Point the shared resolver configuration at the forwarder, then report ready."""
    RESOLV.write_text("nameserver 127.0.0.1\noptions ndots:0 timeout:2 attempts:2\n")
    READY.write_text("ready\n")


async def serve(
    domains: tuple[str, ...], extra: list[str], learned: set[str], refresh_seconds: int
) -> None:
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(lambda: Udp(domains), local_addr=LISTEN)

    connections = asyncio.Semaphore(IN_FLIGHT)

    async def tcp(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if connections.locked():
            writer.close()
            return
        async with connections:
            try:
                size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), 10))[0]
                packet = await asyncio.wait_for(reader.readexactly(size), 10)
                refusal = verdict(packet, domains)
                if refusal is not None:
                    response = refusal
                else:
                    response = screened(packet, await forward_tcp(packet), domains)
                    ANSWERS.record(packet, response)
                writer.write(struct.pack("!H", len(response)) + response)
                await writer.drain()
            except (TimeoutError, OSError, asyncio.IncompleteReadError, struct.error):
                pass
            finally:
                writer.close()

    await asyncio.start_server(tcp, *LISTEN)
    ANSWERS.domains = domains
    await Relay(domains, ANSWERS.of).serve(RELAY_PORT)
    announce()
    log.warning("workspace_netguard_ready domains=%d", len(domains))
    known = [*METAAPI_KNOWN_HOSTS, *domains]
    while True:
        # Every few minutes, or at once when a lookup found a chain into a denied domain.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(ANSWERS.changed.wait(), refresh_seconds)
        ANSWERS.changed.clear()
        try:
            # Grow only: a failed or empty lookup never removes an address already blocked.
            learned.update(await resolve(known))
            await asyncio.to_thread(apply, [*extra, *sorted(learned | ANSWERS.blocked())])
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
    extra = [
        *os.environ.get("LONORA_WORKSPACE_BLOCKED_ADDRESSES", "").split(),
        *os.environ.get("LONORA_WORKSPACE_HOST_ADDRESSES", "").split(),
    ]
    networks(extra)  # refuse a malformed address before anything is installed
    refresh = int(os.environ.get("LONORA_WORKSPACE_GUARD_REFRESH_SECONDS", "300"))
    apply(extra)

    async def run() -> None:
        learned = set(await resolve([*METAAPI_KNOWN_HOSTS, *domains]))
        apply([*extra, *sorted(learned)])
        await serve(domains, extra, learned, refresh)

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
