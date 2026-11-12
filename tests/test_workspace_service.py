"""The workspace service's pure parts: egress rules, the DNS filter, the agent user map,
and the supervisor's request rules. The container behavior itself is proved by
tests/check_workspace_service.py against a real Docker stack."""

import ipaddress
import json
import struct
import uuid
from pathlib import Path

import pytest
from lonora_core.broker_endpoints import BROKER_DOMAINS, METAAPI_KNOWN_HOSTS, METAAPI_SDK_DOMAIN
from lonora_workspace import dns
from lonora_workspace.egress import (
    BLOCKED_V4,
    BLOCKED_V6,
    denied_domains,
    name_denied,
    networks,
    ruleset,
)
from lonora_workspace.netguard import verdict
from lonora_workspace.supervisor import Limits, RunCommand, Supervisor
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
    assert "policy accept" in text and text.count("@blocked4") == 2
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
    assert env["PIP_USER"] == "1" and env["NPM_CONFIG_PREFIX"].endswith("/.local")
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
