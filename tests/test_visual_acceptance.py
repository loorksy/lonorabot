"""The real-model acceptance runner exercises the same nonfinancial runtime path."""

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from sqlalchemy import text
from test_task_runtime import task_db as task_db
from workspace_fake import FakeWorkspace

spec = importlib.util.spec_from_file_location(
    "visual_acceptance", Path(__file__).parents[1] / "scripts/verify_agent_journeys.py"
)
assert spec and spec.loader
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def frame(lines: list[dict[str, Any]]) -> str:
    body = "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
    return "الشرح المختصر.\n```lonora-ui\n" + body + "\n```\nخلاصة المثال."


CLOSE = {"why": "أوضح من فقرة.", "fallback": "الخلاصة نصًا."}


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
        if self.journey in {"visual_workspace", "visual_observed"} and self.calls <= 2:
            name = "tool_environment" if self.calls == 1 else "workspace_run"
            arguments = (
                {"query": "workspace"} if self.calls == 1 else {"command": "wc -c acceptance/*"}
            )
            return ModelReply(
                tool_calls=[ToolCall(id="probe-" + str(self.calls), name=name, arguments=arguments)]
            ), ModelSelection(provider="openai", model="scripted-acceptance")
        value: list[dict[str, Any]]
        if self.journey in {"visual_workspace", "visual_observed"}:
            value = [
                {"v": 2, "kind": "receipt", "title": "حجم الملفات", "mode": "observed"},
                {"facts": {"size": {"call": "probe-2", "path": "/exit_code"}}},
                {"type": "KeyValue", "rows": [["حجم الملف الأول", "{@Fact('size')} بايت"]]},
                CLOSE,
            ]
        elif self.journey == "visual_diagram":
            value = [
                {"v": 2, "kind": "diagram", "title": "مسار الرسالة", "icon": "branch"},
                {"type": "Title", "text": "الطلب"},
                {"type": "Text", "text": "ثم التحليل"},
                {"type": "Text", "text": "ثم النتيجة"},
                CLOSE,
            ]
        elif self.journey == "visual_calculator":
            value = [
                {"v": 2, "kind": "calculator", "title": "حاسبة الوحدات", "mode": "example"},
                {"state": {"risk": 100, "distance": 20}, "calc": {"units": "$risk/$distance"}},
                {"type": "Number", "bind": "risk", "label": "المخاطرة"},
                {"type": "Number", "bind": "distance", "label": "المسافة"},
                {"type": "Text", "text": "الوحدات: {@Fmt($units,2)}"},
                CLOSE,
            ]
        else:
            return ModelReply(text="حقوق الحساب هي الرصيد مضافاً إليه الربح أو الخسارة العائمة."), (
                ModelSelection(provider="openai", model="scripted-acceptance")
            )
        return ModelReply(text=frame(value)), ModelSelection(
            provider="openai", model="scripted-acceptance"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "journey",
    ["visual_plain", "visual_workspace", "visual_observed", "visual_diagram", "visual_calculator"],
)
async def test_acceptance_records_real_runtime_publication_and_cleans_identity(
    task_db: tuple[Database, str, str, str],
    tmp_path: Path,
    journey: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db, owner, _, _ = task_db
    if db.engine.dialect.name == "sqlite":
        async with db.engine.begin() as connection:
            # The production runner relies on real ON DELETE CASCADE receipts.
            await connection.execute(text("PRAGMA foreign_keys=ON"))
    router = ScriptedAcceptanceRouter(journey)
    # The supervisor's stand-in: `wc -c` over the seeded files, as the real one answers.
    files = FakeWorkspace(
        lambda agent, command: {
            "exit_code": 0,
            "duration_ms": 1,
            "stdout_dropped_bytes": 0,
            "stderr_dropped_bytes": 0,
            "stdout": "".join(
                f"{len(body)} {path}\n"
                for (owner_agent, path), body in sorted(files.files.items())
                if owner_agent == agent
            ),
        }
    )
    monkeypatch.setattr(acceptance, "workspace", files.client())
    evidence = tmp_path / "evidence"
    # The real store: workspace output is scanned for the owner's stored secrets.
    secrets = EncryptedSecretStore(db, os.environ["LONORA_ENCRYPTION_KEY"], owner)
    summary = await acceptance.run_journey(
        db,
        owner,
        cast(Any, router),
        secrets,
        acceptance.AcceptanceRegistry(),
        tmp_path,
        journey,
        30,
        evidence,
    )
    assert summary["status"] == "completed"
    assert summary["model_generations"] == (
        3 if journey in {"visual_workspace", "visual_observed"} else 1
    )
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


@pytest.mark.parametrize("malformed", [False, True])
def test_autonomous_presentation_allows_plain_text_but_not_rejected_visuals(malformed: bool):
    from lonora_db.schema import MessageRow

    answer = MessageRow(
        content="تعذر عرض هذا الجزء التفاعلي."
        if malformed
        else "The six actual files total 2245 bytes.",
        rich_content=None,
    )
    observations = {
        "workspace_run": [
            {
                "exit_code": 0,
                "stdout": "".join(
                    f"{len(data)} acceptance/{path}\n"
                    for path, data in acceptance.VISUAL_WORKSPACE_FILES.items()
                ),
            }
        ]
    }
    if malformed:
        with pytest.raises(AssertionError, match="Malformed native output"):
            acceptance.assert_visual_journey("visual_workspace", answer, observations)
    else:
        result = acceptance.assert_visual_journey("visual_workspace", answer, observations)
        assert result["presentation"] == "text" and result["visual_documents"] == 0
