"""The workspace service's pure parts: egress rules, the DNS filter, the agent user map,
and the supervisor's request rules. The container behavior itself is proved by
tests/check_workspace_service.py against a real Docker stack."""

import asyncio
import ipaddress
import json
import os
import shutil
import signal
import struct
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from lonora_core.broker_endpoints import BROKER_DOMAINS, METAAPI_KNOWN_HOSTS, METAAPI_SDK_DOMAIN
from lonora_workspace import dns, netguard, relay
from lonora_workspace.egress import (
    BLOCKED_V4,
    BLOCKED_V6,
    denied_domains,
    name_denied,
    networks,
    ruleset,
)
from lonora_workspace.netguard import verdict
from lonora_workspace.supervisor import Limits, RunCommand, Supervisor, signal_agents
from lonora_workspace.users import AGENTS_GID, FIRST_UID, Users
from pydantic import ValidationError


def test_broker_domains_cover_every_metaapi_host_the_sdk_dials():
    assert METAAPI_SDK_DOMAIN in BROKER_DOMAINS
    for host in METAAPI_KNOWN_HOSTS:
        assert name_denied(host, BROKER_DOMAINS), host
    for discovered in ("mt-client-api-v1.new-york-b.agiliumtrade.ai", "X.AgiliumTrade.AI."):
        assert name_denied(discovered, BROKER_DOMAINS)


def test_only_names_under_a_denied_domain_are_refused():
    domains = denied_domains("Lonora.Example.com")
    assert name_denied("lonora.example.com", domains)
    assert name_denied("api.lonora.example.com", domains)
    for allowed in ("example.com", "notagiliumtrade.ai", "pypi.org", "metaapi.cloud.evil.org"):
        assert not name_denied(allowed, domains), allowed
    with pytest.raises(ValueError):
        denied_domains("bad domain")


def test_every_private_reserved_and_loopback_range_is_rejected():
    v4, v6 = networks([*BLOCKED_V4, *BLOCKED_V6])
    blocked = [ipaddress.ip_network(n) for n in v4 + v6]
    for address in (
        "10.1.2.3",
        "172.17.0.1",
        "172.31.255.254",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "127.0.0.1",
        "0.0.0.0",
        "fd00::1",
        "fe80::1",
        "::ffff:10.0.0.1",
    ):
        ip = ipaddress.ip_address(address)
        assert any(ip in n for n in blocked if n.version == ip.version), address
    for public in ("1.1.1.1", "151.101.0.223", "2606:4700::1111"):
        ip = ipaddress.ip_address(public)
        assert not any(ip in n for n in blocked if n.version == ip.version), public


def test_ruleset_replaces_the_table_in_one_transaction_and_guards_the_docker_resolver():
    text = ruleset(["203.0.113.9", "2001:db8::5"])
    assert text.startswith("add table inet lonora_workspace\ndelete table inet lonora_workspace\n")
    assert 'oifname "lo" ip daddr 127.0.0.11 meta skuid != 0 reject' in text
    assert text.index("127.0.0.11 meta skuid") < text.index('oifname "lo" accept')
    assert "203.0.113.9/32" in text and "2001:db8::5/128" in text
    assert "policy accept" in text and text.count("@blocked4") == 3
    with pytest.raises(ValueError):
        ruleset(["not-an-address"])


def _answer(name: str, records: list[tuple[int, bytes]]) -> bytes:
    query = dns.query(name, dns.A)
    header = query[:2] + struct.pack("!HHHHH", 0x8180, 1, len(records), 0, 0)
    body = query[12:]
    for kind, data in records:
        body += b"\xc0\x0c" + struct.pack("!HHIH", kind, 1, 60, len(data)) + data
    return header + body


def test_dns_filter_refuses_broker_names_and_forwards_the_rest():
    domains = denied_domains("lonora.example.com")
    refused = verdict(dns.query("mt-client-api-v1.london.agiliumtrade.ai", dns.A), domains)
    assert refused is not None and refused[3] & 0x0F == dns.NXDOMAIN and refused[2] & 0x80
    assert verdict(dns.query("API.Lonora.Example.com", dns.AAAA), domains) is not None
    assert verdict(dns.query("pypi.org", dns.A), domains) is None
    garbage = verdict(b"\x00\x01\x80", domains)
    assert garbage is not None and garbage[3] & 0x0F == dns.FORMERR
    pointer = dns.query("pypi.org", dns.A)[:12] + b"\xc0\x0c" + b"\0\1\0\1"
    assert verdict(pointer, domains) is not None


def test_dns_answers_yield_their_addresses_through_compression():
    packet = _answer(
        "metaapi.cloud",
        [(dns.A, bytes([93, 184, 216, 34])), (dns.AAAA, bytes(15) + b"\1"), (5, b"\xc0\x0c")],
    )
    assert dns.addresses(packet) == ["93.184.216.34", "::1"]
    with pytest.raises(dns.DnsError):
        dns.addresses(packet[:-3])


def _etc(tmp_path: Path) -> Path:
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "passwd").write_text(
        "root:x:0:0:root:/root:/bin/bash\nlonora:x:10001:10001::/home/lonora:/bin/sh\n"
    )
    (etc / "group").write_text("root:x:0:\nlonora:x:10001:\n")
    return etc


def test_each_agent_gets_one_stable_uid_kept_on_the_workspace_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def no_chown(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("os.chown", no_chown)
    root, etc = tmp_path / "disk", _etc(tmp_path)
    root.mkdir()
    users = Users(root, etc)
    users.load()
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    assert users.ensure(first) == FIRST_UID
    assert users.ensure(second) == FIRST_UID + 1
    assert users.ensure(first) == FIRST_UID
    assert (root / "home" / f"a{FIRST_UID}").stat().st_mode & 0o777 == 0o700
    assert (root / ".lonora" / "users.json").stat().st_mode & 0o777 == 0o600
    # A new container: the accounts are rebuilt from the disk, image accounts are kept.
    (etc / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\n")
    again = Users(root, etc)
    again.load()
    assert again.ensure(second) == FIRST_UID + 1
    passwd = (etc / "passwd").read_text()
    assert passwd.startswith("root:x:0:0:")
    assert (
        f"a{FIRST_UID}:x:{FIRST_UID}:{FIRST_UID}:Lonora agent:{root}/home/a{FIRST_UID}:/bin/bash"
        in passwd
    )
    group = (etc / "group").read_text()
    assert f"agents:x:{AGENTS_GID}:a{FIRST_UID},a{FIRST_UID + 1}" in group
    assert group.count("agents:x:") == 1
    with pytest.raises(ValueError):
        again.ensure("not-an-agent")


def test_a_corrupt_user_map_is_refused(tmp_path: Path):
    root = tmp_path / "disk"
    (root / ".lonora").mkdir(parents=True)
    (root / ".lonora" / "users.json").write_text(json.dumps({str(uuid.uuid4()): 0}))
    with pytest.raises(ValueError, match="workspace_users_corrupt"):
        Users(root, _etc(tmp_path)).load()


def test_commands_get_a_clean_environment_that_cannot_replace_identity(tmp_path: Path):
    supervisor = Supervisor(Users(tmp_path, _etc(tmp_path)), Limits(foreground_seconds=600))
    env = supervisor.environment(FIRST_UID, {"API_KEY_NAME": "x"})
    assert env["HOME"] == f"{tmp_path}/home/a{FIRST_UID}"
    assert env["PATH"].startswith(f"{tmp_path}/home/a{FIRST_UID}/.local/bin:")
    # No PIP_USER: it breaks pip inside a virtualenv; pip falls back to ~/.local by itself.
    assert "PIP_USER" not in env and env["NPM_CONFIG_PREFIX"].endswith("/.local")
    assert "LONORA_ENCRYPTION_KEY" not in env and env["API_KEY_NAME"] == "x"
    for name in ("HOME", "PATH", "USER", "bad-name", "lower"):
        with pytest.raises(ValueError, match="workspace_environment_invalid"):
            supervisor.environment(FIRST_UID, {name: "x"})


def test_run_requests_are_closed_and_bounded():
    agent = str(uuid.uuid4())
    RunCommand.model_validate({"agent_id": agent, "command": "ls"})
    for bad in (
        {"agent_id": agent, "command": ""},
        {"agent_id": agent, "command": "ls", "uid": 0},
        {"agent_id": "root", "command": "ls"},
        {"agent_id": agent, "command": "ls", "timeout_seconds": 0},
        {"agent_id": agent, "command": "x" * 32769},
    ):
        with pytest.raises(ValidationError):
            RunCommand.model_validate(bad)


def test_foreground_limit_defaults_to_ten_minutes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LONORA_WORKSPACE_FOREGROUND_SECONDS", raising=False)
    assert Limits.from_environment().foreground_seconds == 600
    monkeypatch.setenv("LONORA_WORKSPACE_FOREGROUND_SECONDS", "0")
    with pytest.raises(ValueError):
        Limits.from_environment()


def test_only_the_upstream_reply_to_that_very_query_is_accepted():
    query = dns.query("pypi.org", dns.A)
    genuine = query[:2] + struct.pack("!HHHHH", 0x8180, 1, 0, 0, 0) + query[12:]
    assert dns.answers(query, genuine)
    forged_id = bytes([query[0] ^ 1, query[1]]) + genuine[2:]
    assert not dns.answers(query, forged_id)
    assert not dns.answers(query, query)  # not a reply
    other = dns.query("files.pythonhosted.org", dns.A)
    assert not dns.answers(query, query[:2] + other[2:])
    assert not dns.answers(query, genuine[:12])  # an empty forged reply


def test_answers_that_lead_into_a_broker_domain_are_refused():
    domains = denied_domains(None)
    query = dns.query("innocent.example.org", dns.A)
    target = b"\x0cagiliumtrade\x02ai\x00"
    cname = query[12:-4] + struct.pack("!HHIH", dns.CNAME, 1, 60, len(target)) + target
    answer = query[:2] + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0) + query[12:] + cname
    assert "agiliumtrade.ai" in dns.names(answer)
    screened = netguard.screened(query, answer, domains)
    assert screened[3] & 0x0F == dns.NXDOMAIN
    clean = query[:2] + struct.pack("!HHHHH", 0x8180, 1, 0, 0, 0) + query[12:]
    assert netguard.screened(query, clean, domains) == clean


def test_no_resolver_but_the_forwarder_is_reachable():
    text = ruleset()
    assert "th dport { 53, 853 } reject" in text
    assert text.index('oifname "lo" accept') < text.index("th dport { 53, 853 }")


@pytest.mark.skipif(os.geteuid() != 0, reason="runs a command as an agent user")
def test_a_foreground_command_ends_with_its_own_process(tmp_path: Path):
    root = Path(tempfile.mkdtemp(dir="/tmp"))
    root.chmod(0o755)
    try:
        supervisor = Supervisor(Users(root, _etc(tmp_path)), Limits(foreground_seconds=20))
        supervisor.users.load()

        async def go() -> dict[str, object]:
            request = RunCommand(agent_id=uuid.uuid4(), command="sleep 8 & echo quick")
            return await supervisor.foreground(request)

        started = time.monotonic()
        result = asyncio.run(go())
        assert time.monotonic() - started < 4
        assert result["exit_code"] == 0 and not result["timed_out"]
        assert result["stdout"] == "quick\n"
        signal_agents(signal.SIGKILL, None, supervisor.users)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _hello(name: str | None, ech: bool = False) -> bytes:
    extensions = b""
    if name is not None:
        host = name.encode()
        entry = b"\x00" + struct.pack("!H", len(host)) + host
        listed = struct.pack("!H", len(entry)) + entry
        extensions += struct.pack("!HH", 0, len(listed)) + listed
    if ech:
        extensions += struct.pack("!HH", 0xFE0D, 4) + b"\x00\x01\x02\x03"
    message = (
        b"\x03\x03"
        + bytes(32)
        + b"\x00"
        + struct.pack("!H", 2)
        + b"\x13\x01"
        + b"\x01\x00"
        + struct.pack("!H", len(extensions))
        + extensions
    )
    handshake = b"\x01" + len(message).to_bytes(3, "big") + message
    return b"\x16\x03\x01" + struct.pack("!H", len(handshake)) + handshake


def test_the_relay_reads_the_name_every_connection_asks_for():
    assert relay.requested_name(_hello("pypi.org")) == "pypi.org"
    whole = _hello("mt-client-api-v1.london.agiliumtrade.ai")
    assert relay.requested_name(whole[:20]) is None  # wait for the rest
    assert relay.requested_name(whole) == "mt-client-api-v1.london.agiliumtrade.ai"
    for refused in (_hello(None), _hello("pypi.org", ech=True), b"\x16\x03\x01\x00\x05\x02xxxx"):
        with pytest.raises(relay.Refused):
            relay.requested_name(refused)
    assert (
        relay.requested_name(b"GET / HTTP/1.1\r\nHost: Example.com:8080\r\n\r\n") == "example.com"
    )
    assert relay.requested_name(b"CONNECT app.metaapi.cloud:443 HTTP/1.1\r\nHost: x\r\n\r\n") == (
        "app.metaapi.cloud"
    )
    assert relay.requested_name(b"GET http://metaapi.cloud/x HTTP/1.1\r\nHost: a\r\n\r\n") == (
        "metaapi.cloud"
    )
    assert relay.requested_name(b"GE") is None
    assert relay.requested_name(b"GET / HTTP/1.1\r\nHost") is None
    with pytest.raises(relay.Refused):
        relay.requested_name(b"GET / HTTP/1.1\r\nX: y\r\n\r\n")
    assert relay.requested_name(b"SSH-2.0-OpenSSH_9.6\r\n") == ""  # passes through


def test_every_outbound_agent_connection_is_relayed_except_rejected_addresses():
    text = ruleset()
    relayed = text[text.index("chain relay") : text.index("chain output")]
    assert "type nat hook output priority -100" in relayed
    assert relayed.index("ip daddr @blocked4 return") < relayed.index("redirect to :15001")
    assert "meta skuid != 0 ip daddr != 127.0.0.0/8 meta l4proto tcp redirect" in relayed
    assert "meta skuid != 0 udp dport 443 reject" in text
    # The redirected packet still leaves by eth0 in this hook: let it reach the relay.
    assert text.index("ct status dnat ip daddr 127.0.0.1 tcp dport 15001 accept") < text.index(
        "ip daddr @blocked4 reject"
    )
    assert "meta skuid != 0 ip6 nexthdr tcp reject" in text


def test_an_invalid_request_never_echoes_its_input(tmp_path: Path):
    import httpx
    from lonora_workspace.supervisor import create_app

    supervisor = Supervisor(Users(tmp_path, _etc(tmp_path)), Limits(foreground_seconds=600))
    leaked = "value-that-must-not-echo-1234"

    async def post() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(supervisor))
        async with httpx.AsyncClient(transport=transport, base_url="http://w") as client:
            return await client.post(
                "/v1/run", json={"agent_id": "not-a-uuid", "command": "ls", "env": {"K": leaked}}
            )

    answer = asyncio.run(post())
    assert answer.status_code == 422 and leaked not in answer.text
    assert answer.json()["code"] == "workspace_request_invalid"
