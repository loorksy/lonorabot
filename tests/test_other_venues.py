"""Mandate 9.5: MetaApi accounts trade only through the door; another venue the owner
connected may be traded from the workspace when the owner asks, reported from the venue's
own history, with one notice that it is outside the door's guarantees."""

import re
from pathlib import Path

from lonora_workspace.egress import denied_domains, name_denied

MANUAL = Path(__file__).parents[1] / "packages/agent-runtime/resources/system/lonora.md"


def chapter(name: str) -> str:
    found = re.search(rf"<!-- policy:{name} -->\n(.*?)<!-- /policy -->", MANUAL.read_text(), re.S)
    assert found is not None
    return found.group(1)


def test_metaapi_trades_only_through_the_door_and_is_unreachable_from_the_workspace() -> None:
    assert "A connected broker account trades only through trade_execute/trade_close_positions" in (
        chapter("core")
    )
    domains = denied_domains(None)
    for host in (
        "mt-client-api-v1.london.agiliumtrade.ai",
        "mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai",
    ):
        assert name_denied(host, domains)
    assert not name_denied("api.binance.com", domains)  # another venue stays reachable


def test_another_venue_is_traded_only_on_the_owners_word_and_named_once() -> None:
    core, files, research = chapter("core"), chapter("files"), chapter("research")
    assert "the owner's own request in chat is the only authority to trade it" in core
    assert "Trade it from the workspace only when the owner asks you to in chat" in files
    assert "no mode or card exists for the venue" in files
    assert "tell the owner once that it is outside the door's guarantees" in files
    assert "no server-enforced limit or pause" in files
    # Once per owner, not per agent: USER.md is the profile every agent reads.
    assert "Unless USER.md already says the owner knows this about the venue" in files
    assert "from the venue's own order and trade history" in files
    # Rules that said the workspace or an external venue never trades are gone (0.4).
    assert "never ask analysis code to trade" not in files
    assert "Generic external financial mutations are unsupported" not in research
