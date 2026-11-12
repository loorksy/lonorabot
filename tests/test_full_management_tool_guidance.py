"""Model-visible guidance must agree with the existing financial authority path."""

import pytest
from lonora_db.agent_binding import binding_context
from lonora_db.schema import AgentRow
from lonora_tools.trade import tools


@pytest.mark.parametrize("name", ["trade_execute", "trade_close_positions"])
def test_financial_tool_guidance_distinguishes_standing_grants_from_approval(name: str):
    tool = next(item for item in tools() if item.name == name)
    definition = tool.definition()
    description = definition.description.casefold()

    # Full executes; Ask asks only for a request that adds risk; a close reduces risk.
    if name == "trade_execute":
        assert "in full, or for a risk-reducing request, it executes at once" in description
        assert "in ask, a request that adds risk" in description
        assert "active signed grant" in description and "trade approval card" in description
    else:
        assert "executes without a card in full and in ask" in description
    assert "reconcile" in description
    assert tool.financial and not tool.read_only and tool.replay_safe
    assert "account_id" in definition.parameters["properties"]
    assert "operation_id" not in definition.parameters["properties"]
    assert tool.environment()["purpose"] == definition.description


def test_personal_agent_guidance_does_not_contradict_signed_management():
    agent = AgentRow(
        id="personal",
        owner_id="owner",
        role="personal",
    )
    guidance = binding_context(agent)

    assert "your trading mode decides execution: full executes on its own" in guidance.casefold()
    assert "uses the existing approval controls unless an active signed account grant" in guidance
    assert "global trading and emergency controls" in guidance
    assert "Owner-wide visibility is NOT autonomous execution authority" in guidance
