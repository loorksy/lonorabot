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
    assert "MetaApi accounts trade only through trade_execute/trade_close_positions" in chapter(
        "core"
    )
    domains = denied_domains(None)
    for host in (
        "mt-client-api-v1.london.agiliumtrade.ai",
        "mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai",
    ):
        assert name_denied(host, domains)
    assert not name_denied("api.binance.com", domains)  # another venue stays reachable


def test_another_venue_is_traded_only_on_the_owners_word_and_named_once() -> None:
    core, files = chapter("core"), chapter("files")
    assert "trade it from the workspace only when the owner asks" in core
    assert "Trade it from the workspace only when the owner asks you to" in files
    assert "tell the owner once that it is outside the door's guarantees" in files
    assert "Record in MEMORY.md that you told them, and do not repeat it." in files
    assert "from the venue's own order and trade history" in files
    # The rule it replaces said the workspace never trades (0.4: the text matches 9.5).
    assert "never ask analysis code to trade" not in files
