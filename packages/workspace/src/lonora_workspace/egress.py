"""What the workspace may not reach (7.1.4), as nftables rules and a name filter.

The workspace shares the network namespace of the guard container and has no network
capability of its own. The guard installs these rules in that namespace: every packet
to a private, link-local, loopback-adjacent or reserved range, to Lonora's own public
address, or to a resolved MetaApi address is rejected; Docker's embedded resolver is
reachable only by root (the guard's own forwarder), and no other resolver is reachable
(DNS and DNS-over-TLS ports are rejected off the host), so every name goes through the
forwarder. Names under a broker domain or Lonora's domain, and answers that lead into
one, do not resolve.
"""

import ipaddress
import re
from collections.abc import Iterable

from lonora_core.broker_endpoints import BROKER_DOMAINS, under

TABLE = "lonora_workspace"
DOCKER_RESOLVER = "127.0.0.11"
BLOCKED_V4 = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
)
BLOCKED_V6 = (
    "::/127",
    "::ffff:0:0/96",
    "64:ff9b::/96",
    "64:ff9b:1::/48",
    "100::/64",
    "2001:db8::/32",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8",
)
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def domain_name(value: str) -> str:
    name = value.strip().lower().rstrip(".")
    if not name or len(name) > 253 or not all(_LABEL.match(p) for p in name.split(".")):
        raise ValueError("workspace_domain_invalid")
    return name


def denied_domains(lonora_domain: str | None, extra: Iterable[str] = ()) -> tuple[str, ...]:
    names = [*BROKER_DOMAINS, *(domain_name(name) for name in extra)]
    if lonora_domain:
        names.append(domain_name(lonora_domain))
    return tuple(dict.fromkeys(names))


def name_denied(name: str, domains: Iterable[str]) -> bool:
    return any(under(name, domain) for domain in domains)


def networks(values: Iterable[str]) -> tuple[list[str], list[str]]:
    v4: list[str] = []
    v6: list[str] = []
    for value in values:
        network = ipaddress.ip_network(value.strip(), strict=False)
        (v4 if network.version == 4 else v6).append(str(network))
    return v4, v6


def _elements(values: Iterable[str]) -> str:
    unique = sorted(dict.fromkeys(values))
    return f" elements = {{ {', '.join(unique)} }};" if unique else ""


def ruleset(extra: Iterable[str] = ()) -> str:
    """One nft transaction that replaces the whole table, so no rule is ever missing."""
    v4, v6 = networks([*BLOCKED_V4, *BLOCKED_V6, *extra])
    return f"""add table inet {TABLE}
delete table inet {TABLE}
table inet {TABLE} {{
  set blocked4 {{ type ipv4_addr; flags interval; auto-merge;{_elements(v4)} }}
  set blocked6 {{ type ipv6_addr; flags interval; auto-merge;{_elements(v6)} }}
  chain output {{
    type filter hook output priority 0; policy accept;
    oifname "lo" ip daddr {DOCKER_RESOLVER} meta skuid != 0 reject
    oifname "lo" accept
    meta l4proto {{ tcp, udp }} th dport {{ 53, 853 }} reject
    meta l4proto tcp ip daddr @blocked4 reject with tcp reset
    ip daddr @blocked4 reject with icmpx type admin-prohibited
    meta l4proto tcp ip6 daddr @blocked6 reject with tcp reset
    ip6 daddr @blocked6 reject with icmpx type admin-prohibited
  }}
}}
"""
