"""The smallest DNS a filtering forwarder needs: read a query's name, answer NXDOMAIN,
build an address query, and read the addresses out of an answer."""

import ipaddress
import secrets
import struct

A, CNAME, AAAA, DNAME = 1, 5, 28, 39
NOERROR, FORMERR, NXDOMAIN = 0, 1, 3


class DnsError(ValueError):
    pass


def _name(packet: bytes, offset: int, depth: int = 0) -> tuple[str, int]:
    labels: list[str] = []
    while True:
        if offset >= len(packet) or depth > 16:
            raise DnsError("dns_name_invalid")
        length = packet[offset]
        if length == 0:
            return ".".join(labels), offset + 1
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise DnsError("dns_name_invalid")
            pointer = struct.unpack("!H", packet[offset : offset + 2])[0] & 0x3FFF
            rest, _ = _name(packet, pointer, depth + 1)
            return ".".join([*labels, rest] if rest else labels), offset + 2
        if length & 0xC0:
            raise DnsError("dns_name_invalid")
        label = packet[offset + 1 : offset + 1 + length]
        if len(label) != length:
            raise DnsError("dns_name_invalid")
        labels.append(label.decode("ascii", "replace").lower())
        offset += 1 + length


def question(packet: bytes) -> tuple[str, int]:
    """The one question of a query, without following pointers (a query never needs them).
    Returns the name and the offset just after the question."""
    if len(packet) < 12:
        raise DnsError("dns_query_short")
    flags, qdcount = struct.unpack("!HH", packet[2:6])
    if flags & 0x8000 or qdcount != 1:
        raise DnsError("dns_query_invalid")
    labels: list[str] = []
    offset = 12
    while True:
        if offset >= len(packet):
            raise DnsError("dns_query_short")
        length = packet[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 or offset + 1 + length > len(packet):
            raise DnsError("dns_query_invalid")
        labels.append(packet[offset + 1 : offset + 1 + length].decode("ascii", "replace").lower())
        offset += 1 + length
    if offset + 4 > len(packet):
        raise DnsError("dns_query_short")
    return ".".join(labels), offset + 4


def reply(packet: bytes, rcode: int) -> bytes:
    """An answer with no records and `rcode`, echoing the query's id and question."""
    ident = packet[:2] if len(packet) >= 2 else b"\0\0"
    try:
        _, end = question(packet)
        body, qdcount = packet[12:end], 1
    except DnsError:
        body, qdcount = b"", 0
    recursion = struct.unpack("!H", packet[2:4])[0] & 0x0100 if len(packet) >= 4 else 0
    flags = 0x8000 | 0x0080 | recursion | (rcode & 0xF)
    return ident + struct.pack("!HHHHH", flags, qdcount, 0, 0, 0) + body


def query(name: str, kind: int) -> bytes:
    header = struct.pack("!HHHHHH", secrets.randbelow(65536), 0x0100, 1, 0, 0, 0)
    encoded = b"".join(
        bytes([len(label)]) + label.encode("ascii") for label in name.rstrip(".").split(".")
    )
    return header + encoded + b"\0" + struct.pack("!HH", kind, 1)


def addresses(packet: bytes) -> list[str]:
    """The A and AAAA records of an answer (any owner name: CNAME chains included)."""
    if len(packet) < 12:
        raise DnsError("dns_answer_short")
    qdcount, ancount = struct.unpack("!HH", packet[4:8])
    offset = 12
    for _ in range(qdcount):
        _, offset = _name(packet, offset)
        offset += 4
    found: list[str] = []
    for _ in range(ancount):
        _, offset = _name(packet, offset)
        if offset + 10 > len(packet):
            raise DnsError("dns_answer_short")
        kind, _, _, size = struct.unpack("!HHIH", packet[offset : offset + 10])
        data = packet[offset + 10 : offset + 10 + size]
        if len(data) != size:
            raise DnsError("dns_answer_short")
        if kind == A and size == 4 or kind == AAAA and size == 16:
            found.append(str(ipaddress.ip_address(data)))
        offset += 10 + size
    return found


def answers(query_packet: bytes, answer: bytes) -> bool:
    """True when `answer` is a reply to exactly `query_packet` (id, flag, question)."""
    try:
        _, end = question(query_packet)
    except DnsError:
        return False
    return (
        len(answer) >= end
        and answer[:2] == query_packet[:2]
        and bool(answer[2] & 0x80)
        and answer[4:6] == b"\0\1"
        and answer[12:end].lower() == query_packet[12:end].lower()
    )


def names(packet: bytes) -> list[str]:
    """Every name an answer leads to: the owners of its answer records and CNAME/DNAME
    targets."""
    if len(packet) < 12:
        raise DnsError("dns_answer_short")
    qdcount, ancount = struct.unpack("!HH", packet[4:8])
    offset = 12
    for _ in range(qdcount):
        _, offset = _name(packet, offset)
        offset += 4
    found: list[str] = []
    # The answer section only: an authority or additional record names who serves a
    # zone, not where the asked name leads.
    for _ in range(ancount):
        owner, offset = _name(packet, offset)
        if offset + 10 > len(packet):
            raise DnsError("dns_answer_short")
        kind, _, _, size = struct.unpack("!HHIH", packet[offset : offset + 10])
        found.append(owner)
        if kind in (CNAME, DNAME):
            found.append(_name(packet, offset + 10)[0])
        offset += 10 + size
    return found


def owned_addresses(packet: bytes) -> list[tuple[str, str]]:
    """(owner name, address) of every A and AAAA answer record."""
    if len(packet) < 12:
        raise DnsError("dns_answer_short")
    qdcount, ancount = struct.unpack("!HH", packet[4:8])
    offset = 12
    for _ in range(qdcount):
        _, offset = _name(packet, offset)
        offset += 4
    found: list[tuple[str, str]] = []
    for _ in range(ancount):
        owner, offset = _name(packet, offset)
        if offset + 10 > len(packet):
            raise DnsError("dns_answer_short")
        kind, _, _, size = struct.unpack("!HHIH", packet[offset : offset + 10])
        data = packet[offset + 10 : offset + 10 + size]
        if kind == A and size == 4 or kind == AAAA and size == 16:
            found.append((owner, str(ipaddress.ip_address(data))))
        offset += 10 + size
    return found
