"""The real-model acceptance runner exercises the same nonfinancial runtime path."""

import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from sqlalchemy import text
from test_task_runtime import task_db as task_db

spec = importlib.util.spec_from_file_location(
    "visual_acceptance", Path(__file__).parents[1] / "scripts/verify_agent_journeys.py"
)
assert spec and spec.loader
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def frame(document: dict[str, Any]) -> str:
    return "الشرح المختصر.\n```lonora-ui\n" + json.dumps(document) + "\n```\nخلاصة المثال."


class ScriptedAcceptanceRouter:
    credentials = None

    def __init__(self, journey: str):
        self.journey = journey
        self.calls = 0

    async def complete(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        **kwargs: Any,
    ) -> tuple[ModelReply, ModelSelection]:
        self.calls += 1
        if self.journey == "visual_workspace" and self.calls <= 2:
            name = "tool_environment" if self.calls == 1 else "workspace_inspect"
            arguments = {"query": "workspace"} if self.calls == 1 else {}
            return ModelReply(
                tool_calls=[ToolCall(id="probe-" + str(self.calls), name=name, arguments=arguments)]
            ), ModelSelection(provider="openai", model="scripted-acceptance")
        value: dict[str, Any] = {"version": 1, "mode": "example", "root": {}}
        if self.journey == "visual_workspace":
            value["mode"] = "observed"
            value["root"] = {
                "id": "size",
                "type": "metric",
                "label": "حجم الملف الأول",
                "value": {"fact": {"call_id": "probe-2", "path": "/files/0/size"}},
                "unit": "bytes",
            }
        elif self.journey == "visual_diagram":
            value["root"] = {
                "id": "flow",
                "type": "diagram",
                "vertices": [
                    {"id": "request", "label": "الطلب"},
                    {"id": "analysis", "label": "التحليل"},
                    {"id": "result", "label": "النتيجة"},
                ],
                "edges": [
                    {"source": "request", "target": "analysis"},
                    {"source": "analysis", "target": "result"},
                ],
            }
        elif self.journey == "visual_calculator":
            value["state"] = {"risk": 100, "distance": 20}
            value["root"] = {
                "id": "calculator",
                "type": "column",
                "children": [
                    {
                        "id": "risk-input",
                        "type": "input",
                        "label": "المخاطرة الافتراضية",
                        "input_kind": "number",
                        "state_key": "risk",
                        "minimum": 1,
                        "maximum": 1000,
                    },
                    {
                        "id": "distance-input",
                        "type": "input",
                        "label": "المسافة الافتراضية",
                        "input_kind": "number",
                        "state_key": "distance",
                        "minimum": 1,
                        "maximum": 100,
                    },
                    {
                        "id": "units",
                        "type": "metric",
                        "label": "عدد الوحدات الافتراضية",
                        "value": {
                            "op": "div",
                            "args": [{"state": "risk"}, {"state": "distance"}],
                        },
                    },
                ],
            }
        else:
            return ModelReply(text="حقوق الحساب هي الرصيد مضافاً إليه الربح أو الخسارة العائمة."), (
                ModelSelection(provider="openai", model="scripted-acceptance")
            )
        return ModelReply(text=frame(value)), ModelSelection(
            provider="openai", model="scripted-acceptance"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "journey", ["visual_plain", "visual_workspace", "visual_diagram", "visual_calculator"]
)
async def test_acceptance_records_real_runtime_publication_and_cleans_identity(
    task_db: tuple[Database, str, str, str], tmp_path: Path, journey: str
):
    db, owner, _, _ = task_db
    if db.engine.dialect.name == "sqlite":
        async with db.engine.begin() as connection:
            # The production runner relies on real ON DELETE CASCADE receipts.
            await connection.execute(text("PRAGMA foreign_keys=ON"))
    router = ScriptedAcceptanceRouter(journey)
    evidence = tmp_path / "evidence"
    summary = await acceptance.run_journey(
        db,
        owner,
        cast(Any, router),
        None,
        acceptance.AcceptanceRegistry(),
        tmp_path,
        journey,
        30,
        evidence,
    )
    assert summary["status"] == "completed"
    assert summary["model_generations"] == (3 if journey == "visual_workspace" else 1)
    record = json.loads((evidence / (journey + ".json")).read_text())
    assert record["journey"] == journey
    assert record["content"] and "```lonora-ui" not in record["content"]
    assert bool(record["rich_content"]) == (journey != "visual_plain")


@pytest.mark.asyncio
async def test_acceptance_cannot_acquire_financial_services_or_execute_financial_action():
    denied = acceptance.DeniedService()
    with pytest.raises(AssertionError, match="financial service"):
        denied.execute()
    registry = acceptance.AcceptanceRegistry()
    with pytest.raises(LonoraError, match="acceptance_tool_denied"):
        await registry.execute(ToolCall(id="forged", name="trade_execute", arguments={}), None)
