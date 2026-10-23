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

    assert "active signed account grant" in description
    assert "without per-order confirmation" in description
    assert "otherwise propose" in description
    assert "approve and reject" in description
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
        execution_mode="live",
    )
    guidance = binding_context(agent)

    assert "active signed account grant permits matching actions" in guidance
    assert (
        "without per-order confirmation; otherwise use the existing approval controls" in guidance
    )
    assert "global trading and emergency controls" in guidance
    assert "Owner-wide visibility is NOT autonomous execution authority" in guidance
