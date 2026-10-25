"""Explicit, real-model acceptance of nonfinancial Lonora journeys.

Run inside the deployed Gateway/API environment:
    python scripts/verify_agent_journeys.py --allow-live-model

Uses one existing owner's configured provider credential only through its normal
router. It creates active temporary identities with 24-hour pre-leased runs
to exclude normal Gateway scheduling, then invokes the real AgentRuntime. No financial or broker
capability, task spawning, package installation or external messaging is exposed.
All diagnostic rows/files are removed in finally. The model consumes real tokens.
"""

import argparse
import asyncio
import hashlib
import json
import re
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_agent.executor import execute_run
from lonora_agent.skills.access import view_key
from lonora_agent.workspace import encode_snapshot
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_agent.workspace_client import WorkspaceClient
from lonora_api.env import get_settings
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.runs import Lease
from lonora_contracts.visual_response import RichContent, VisualDocument, VisualNode
from lonora_core.model_routing import select_model
from lonora_core.public_reply import public_reply_violation
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import (
    AgentRow,
    AnalyticalWorkspaceRow,
    ArtifactRow,
    EffectReceiptRow,
    EventRow,
    MessageRow,
    OwnerRow,
    RunRow,
    ThreadRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.router import GlobalModelRouter
from lonora_providers.routing_policy import read_policy
from lonora_security.runtime_storage import confined_path
from lonora_session.idempotency import stable_id
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from sqlalchemy import delete, func, or_, select

LEASE_SECONDS = 24 * 60 * 60

ALLOWED = frozenset(
    {
        "skills_list",
        "skill_view",
        "wait_for_input",
        "skill_repository_inspect",
        "web_fetch",
        "workspace_inspect",
        "workspace_read",
        "workspace_update",
        "workspace_execute",
        "workspace_export",
        "artifact_read",
    }
)
JOURNEYS = {
    "repository": (
        "افحص هذا المستودع وقل لي ما الذي يقدمه للتداول وما أهم حدوده، "
        "اعتمد على قراءة فعلية لمحتواه ولا تثبّت أو تشغّل أي شيء منه: "
        "https://github.com/Jakeschincariol/day-trader-skill"
    ),
    "report": (
        "احسب مجموع مربعات الأعداد من 1 إلى 20 باستخدام بايثون فعلياً، "
        "واحفظ النتيجة في ملف تقرير نصي باسم calculation-report.txt وأرفقه هنا. "
        "لا ترسل مجرد كود لأن المطلوب النتيجة المحسوبة والملف الجاهز."
    ),
    "capabilities": "طيب بدي منك قائمة جميع ادواتك",
    "topic_switch": "ما الفرق بين السكالبينغ والسوينغ باختصار؟",
    "visual_plain": "ما معنى حقوق الحساب (Equity) بجملة واحدة؟",
    "visual_workspace": (
        "راجع الملفات الموجودة فعلاً في مساحة التحليل وقارن أحجامها، واجمع حجمها الإجمالي، "
        "وبيّن توزيع الأحجام وما يستحق تنظيمه أولاً. اعتمد على الفحص الفعلي ولا تعدّل أي ملف. "
        "اختر طريقة العرض الأنسب لتوضيح المقارنة."
    ),
    "visual_diagram": (
        "اشرح مسار رسالة المستخدم داخل Lonora بمخطط أصلي داخل الرد: فهم الطلب، "
        "العمليات المتاحة عند الحاجة، التحقق، ثم النتيجة المحفوظة. لا أريد ملفاً أو كوداً "
        "أو صورة، بل مخططاً بأسماء عربية وروابط مرئية ومعه شرح قصير."
    ),
    "visual_calculator": (
        "ساعدني أفهم حجم المركز بحاسبة تعليمية تفاعلية داخل الرد. هذا مثال لعقد افتراضي "
        "فقط، قيمة النقطة فيه دولار واحد لكل وحدة؛ ليس أداة مالية حقيقية ولا حساباً فعلياً. "
        "ابدأ بمخاطرة 100 دولار ومسافة وقف 20 نقطة. أريد تغيير المخاطرة ومسافة الوقف "
        "محلياً ورؤية حجم الوحدات يتغير مباشرة، دون تنفيذ أي صفقة أو إرسال سؤال جديد. "
        "بيّن الافتراضات بوضوح واكتب شرحاً قصيراً قبل الحاسبة وبعدها."
    ),
}
TOPIC_SWITCH_REQUEST = "خلينا نغيّر الموضوع: احسب سبعة ضرب ثمانية وأجب بالنتيجة فقط."
VISUAL_JOURNEYS = frozenset(name for name in JOURNEYS if name.startswith("visual_"))
# Real isolated workspace contents, not fabricated financial/account observations.
VISUAL_WORKSPACE_FILES = {
    "notes.txt": b"Review candidate observations.\n" * 3,
    "session-plan.md": b"# Session plan\nConfirm the current evidence before acting.\n" * 7,
    "journal.csv": b"date,observation\n2026-10-25,educational review\n" * 11,
    "summary.json": b'{"purpose":"nonfinancial acceptance","status":"example"}\n',
    "symbols.csv": b"label,description\nSample,not a live instrument\n" * 2,
    "report.txt": b"This workspace contains synthetic documents, not account data.\n" * 17,
}


def visual_nodes(node: VisualNode) -> list[VisualNode]:
    return [node, *(descendant for child in node.children for descendant in visual_nodes(child))]


def visual_documents(answer: MessageRow) -> list[VisualDocument]:
    if answer.rich_content is None:
        return []
    rich = RichContent.model_validate(answer.rich_content)
    return [part.document for part in rich.parts if part.type == "ui"]


def assert_visual_journey(
    journey: str, answer: MessageRow, observations: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Inspect actual persisted model composition, without prescribing a template."""
    docs = visual_documents(answer)
    nodes = [node for doc in docs for node in visual_nodes(doc.root)]
    if journey == "visual_plain":
        assert not docs, "A one-sentence definition acquired an unnecessary visual"
        assert not observations, "A simple definition unexpectedly invoked operations"
    else:
        assert docs, "The real model reply did not publish a valid native visual"
        assert "```lonora-ui" not in answer.content, "Raw visual protocol reached public text"
        assert nodes, "The model's visual document contains no native components"
    if journey == "visual_workspace":
        inspections = [
            value
            for value in observations.get("workspace_inspect", [])
            if value.get("ok") is not False
        ]
        assert inspections, "No real workspace inspection was performed"
        assert any(
            {item["path"]: item["size"] for item in value.get("files", [])}
            == {path: len(data) for path, data in VISUAL_WORKSPACE_FILES.items()}
            for value in inspections
        ), "Inspected files do not match the actual isolated workspace"
        observed = [doc for doc in docs if doc.mode == "observed"]
        assert observed and any(doc.facts for doc in observed), (
            "No verified observations in the visual"
        )
        assert all(fact.source in ALLOWED for doc in observed for fact in doc.facts.values()), (
            "Observed visual included data from an unexpected operation"
        )
    elif journey == "visual_diagram":
        assert any(
            node.type == "diagram" and len(node.vertices) >= 3 and len(node.edges) >= 2
            for node in nodes
        ), "The real model did not compose a connected native diagram"
    elif journey == "visual_calculator":
        numeric_controls = [
            node
            for node in nodes
            if node.type == "slider" or (node.type == "input" and node.input_kind == "number")
        ]
        assert len(numeric_controls) >= 2, "Calculator is missing adjustable risk/stop inputs"
        assert any(
            node.type == "metric" and isinstance(node.value, dict) and "op" in node.value
            for node in nodes
        ), "Calculator has no locally derived numeric result"
        assert all(doc.mode in {"example", "estimate"} for doc in docs), (
            "Hypothetical instrument was presented as an observed account"
        )
        assert set(observations) <= {"tool_environment", "skills_list", "skill_view"}, (
            "This self-contained illustrative calculator invoked unrelated operations"
        )
        rich = RichContent.model_validate(answer.rich_content)
        assert any(part.type == "text" for part in rich.parts), "Mixed prose was not preserved"
    return {
        "presentation": "native" if docs else "text",
        "visual_documents": len(docs),
        "native_components": sorted({node.type for node in nodes}),
        "verified_facts": sum(len(doc.facts) for doc in docs),
        "compiled_ui_bytes": len(json.dumps(answer.rich_content, ensure_ascii=False).encode())
        if docs
        else 0,
    }


def write_visual_evidence(directory: Path, journey: str, answer: MessageRow) -> None:
    """Export only public nonfinancial composition for subsequent native UI checks."""
    assert journey in VISUAL_JOURNEYS
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (journey + ".json")
    payload = {"journey": journey, "content": answer.content, "rich_content": answer.rich_content}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    path.chmod(0o600)


def assert_capability_explanation(answer: str, catalog: ToolRegistry) -> None:
    """Require meaningful current abilities, without prescribing their phrasing."""
    assert re.search(r"[\u0620-\u064a]", answer), "Capability explanation is not in Arabic"
    categories = (
        ("web_fetch", "skill_repository_inspect", "بحث", "روابط", "مستودع", "مصادر", "ويب"),
        ("workspace_execute", "workspace_update", "بايثون", "حساب", "تحليل", "تنفيذ", "أوامر"),
        (
            "workspace_export",
            "workspace_read",
            "artifact_read",
            "ملف",
            "ملفات",
            "تقرير",
            "تقارير",
            "مرفق",
        ),
        ("skills_list", "skill_view", "مهارات", "إجراءات", "اجراءات"),
        ("wait_for_input", "استيضاح", "توضيح", "سؤال", "أسئلة"),
    )
    matched = sum(
        any(label.casefold() in answer.casefold() for label in group) for group in categories
    )
    available = {tool.name for tool in catalog.discovery_definitions(discovered_names=set(ALLOWED))}
    mentioned = {
        name for name in available if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", answer)
    }
    assert matched >= 2 or len(mentioned) >= 2, (
        "Capability answer does not explain the current permitted catalog"
    )


class AcceptanceRegistry(ToolRegistry):
    """Keep first-party manifest validation while restricting callable presentation.

    Built-in manifest completeness validates against definitions(), not merely
    the currently advertised surface. All search/list/inspection and native
    schemas below use the allowlist; execute independently rejects other names.
    """

    def __init__(self) -> None:
        full = load_tools()
        assert ALLOWED <= set(full.tools)
        super().__init__([tool for name, tool in full.tools.items() if name != "tool_environment"])
        self.catalog = ToolRegistry([full.tools[name] for name in sorted(ALLOWED)])
        assert not any(tool.financial for tool in self.catalog.tools.values())

    def discovery_definitions(
        self, read_only: bool = False, discovered_names: set[str] | None = None
    ) -> list[ToolDefinition]:
        return self.catalog.discovery_definitions(read_only, discovered_names)

    def capability_inventory(self, read_only: bool = False) -> str:
        return self.catalog.capability_inventory(read_only)

    async def inspect_environment(
        self, context: ToolContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.catalog.inspect_environment(context, arguments)

    async def execute(
        self, call: ToolCall, context: ToolContext, read_only: bool = False
    ) -> dict[str, Any]:
        if call.name not in ALLOWED | {"tool_environment"}:
            raise LonoraError("acceptance_tool_denied", 403)
        return await super().execute(call, context, read_only)


class AcceptanceRouter:
    """Reject out-of-scope proposals before they reach any ToolLoop effect path."""

    def __init__(self, router: GlobalModelRouter):
        self.router = router
        self.credentials = router.credentials
        self.model_calls = 0

    async def complete(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        on_attempt: Callable[[ModelSelection], Awaitable[None]] | None = None,
    ) -> tuple[ModelReply, ModelSelection]:
        self.model_calls += 1
        reply, selection = await self.router.complete(
            capability, messages, tools, on_delta=on_delta, on_attempt=on_attempt
        )
        if any(call.name not in ALLOWED | {"tool_environment"} for call in reply.tool_calls):
            raise LonoraError("acceptance_tool_denied", 403)
        return reply, selection


class DeniedService:
    """A diagnostic context cannot accidentally acquire a broker/service handle."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError("Live financial service is unavailable in acceptance: " + name)


def observe_results(row: RunRow) -> dict[str, list[dict[str, Any]]]:
    messages = [
        ModelMessage.model_validate(item) for item in row.execution_state.get("messages", [])
    ]
    calls = {call.id: call for message in messages for call in message.tool_calls}
    results: dict[str, list[dict[str, Any]]] = {}
    for message in messages:
        call = calls.get(message.tool_call_id or "")
        if message.role != "tool" or call is None:
            continue
        if call.name not in ALLOWED | {"tool_environment"}:
            raise AssertionError("Model attempted a capability outside acceptance allowlist")
        try:
            result = json.loads(message.content)
        except ValueError:
            continue
        if isinstance(result, dict):
            results.setdefault(call.name, []).append(cast(dict[str, Any], result))
    return results


async def run_journey(
    db: Database,
    owner_id: str,
    router: GlobalModelRouter,
    secrets: Any,
    registry: ToolRegistry,
    artifact_root: Path,
    journey: str,
    seconds: float,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    agent_id, thread_id, run_id = str(uuid4()), str(uuid4()), str(uuid4())
    worker = "acceptance:" + uuid4().hex
    lease = Lease(run_id=run_id, owner=worker, fence=1)
    context: ToolContext | None = None
    contexts: dict[str, ToolContext] = {}
    run_ids = [run_id]
    created = True
    started = time.monotonic()
    history = (
        [
            ("user", "هل تستطيع قراءة الروابط وتشغيل حسابات بايثون؟"),
            ("assistant", "لا أستطيع فتح روابط أو تشغيل بايثون، يمكنني شرح التعليمات فقط."),
            ("user", JOURNEYS[journey]),
        ]
        if journey == "capabilities"
        else [("user", JOURNEYS[journey])]
    )
    try:
        async with db.sessions() as session, session.begin():
            # A 24-hour explicit lease keeps the ordinary Gateway claimant away
            # during this bounded acceptance. The outer runner must clean the
            # diagnostic identity if the process is killed before finally runs.
            # Keep the identity active: workspace mutations correctly reject
            # paused agents, and acceptance must preserve that real boundary.
            session.add(
                AgentRow(
                    id=agent_id,
                    owner_id=owner_id,
                    role="legacy",
                    name="Acceptance " + journey + " " + uuid4().hex[:8],
                    paused=False,
                    instructions=(
                        "This is a nonfinancial acceptance request with an active runner-owned lease. "
                        "Complete the owner request using actual available operations, then report "
                        "only verified results in Arabic. Never access a broker, account, "
                        "colleague, external message destination or install anything."
                    ),
                )
            )
            await session.flush()
            session.add(
                ThreadRow(
                    id=thread_id, owner_id=owner_id, agent_id=agent_id, next_seq=len(history) + 1
                )
            )
            await session.flush()
            if journey == "visual_workspace":
                session.add(
                    AnalyticalWorkspaceRow(
                        agent_id=agent_id,
                        revision=1,
                        snapshot=encode_snapshot(VISUAL_WORKSPACE_FILES),
                    )
                )
            for seq, (role, content) in enumerate(history, start=1):
                session.add(
                    MessageRow(
                        thread_id=thread_id,
                        agent_id=agent_id,
                        seq=seq,
                        role=role,
                        content=content,
                    )
                )
            session.add(
                RunRow(
                    id=run_id,
                    thread_id=thread_id,
                    agent_id=agent_id,
                    status="leased",
                    trigger="user",
                    prompt="",
                    input_seq=len(history),
                    lease_owner=worker,
                    lease_fence=1,
                    lease_expires_at=utcnow() + timedelta(seconds=LEASE_SECONDS),
                    model_metadata={"acceptance_probe": True},
                )
            )
        created = True
        denied = DeniedService()
        acceptance_router = AcceptanceRouter(router)
        context = ToolContext(
            db=db,
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            lease=lease,
            brokers=cast(Any, denied),
            trading=cast(Any, denied),
            secrets=secrets,
            router=cast(Any, acceptance_router),
            artifact_root=artifact_root,
            maximum_subagents=0,
            workspace_access=RunWorkspaceAccess(
                WorkspaceClient(settings.workspace_socket) if settings.workspace_socket else None
            ),
        )
        contexts[run_id] = context
        async with asyncio.timeout(seconds):
            await execute_run(context, registry, LEASE_SECONDS, maximum_rounds=16)
        async with db.sessions() as session:
            row = await session.get(RunRow, run_id)
            assert row is not None
            observations = observe_results(row)
            summary = {
                "journey": journey,
                "status": row.status,
                "error_code": row.error_code,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "model_generations": acceptance_router.model_calls,
                "successful_operations": sorted(
                    name
                    for name, values in observations.items()
                    if any(v.get("ok") is not False for v in values)
                ),
                "operation_errors": sorted(
                    {
                        str(v.get("code"))
                        for values in observations.values()
                        for v in values
                        if v.get("ok") is False
                    }
                ),
            }
            print(json.dumps(summary), flush=True)
            assert row.status == "completed", "Journey did not complete: " + str(
                row.error_code or row.status
            )
            assert row.result and not public_reply_violation(row.result)
            answer = await session.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == thread_id, MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            assert answer is not None and answer.content == row.result
            if journey in VISUAL_JOURNEYS:
                summary.update(assert_visual_journey(journey, answer, observations))
                assert answer.rich_content == row.model_metadata.get("rich_content"), (
                    "Published composition differs from the settled Agent reply"
                )
                if evidence_dir is not None:
                    write_visual_evidence(evidence_dir, journey, answer)
                print(json.dumps(summary), flush=True)
            assert not await session.scalar(
                select(func.count())
                .select_from(TradingJournalRow)
                .where(
                    TradingJournalRow.operation_id.in_(
                        [
                            stable_id(run_id, call.id)
                            for raw in cast(list[Any], row.execution_state.get("messages", []))
                            for call in ModelMessage.model_validate(raw).tool_calls
                        ]
                    )
                )
            )
            assert not await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.agent_id == agent_id)
            )
            if journey == "capabilities":
                assert_capability_explanation(answer.content, registry)
            elif journey == "topic_switch":
                # The first reply must complete naturally. A separate real turn
                # below changes subjects in the same canonical conversation.
                assert answer.content.strip()
            elif journey == "repository":
                repo = [
                    v
                    for v in observations.get("skill_repository_inspect", [])
                    if v.get("ok") is not False
                ]
                fetched = [
                    v
                    for v in observations.get("web_fetch", [])
                    if v.get("ok") is not False
                    and "github.com/Jakeschincariol/day-trader-skill" in str(v.get("source", ""))
                ]
                assert repo or fetched, "No actual repository source was read"
                if repo:
                    assert any(
                        v.get("repository_url")
                        == "https://github.com/Jakeschincariol/day-trader-skill"
                        and v.get("skills")
                        and v.get("code_executed") is False
                        for v in repo
                    )
            elif journey == "report":
                executed = [
                    v
                    for v in observations.get("workspace_execute", [])
                    if v.get("ok") is not False and v.get("exit_code") == 0
                ]
                assert executed, "No successful actual execution"
                executed_calls = [
                    call
                    for raw in cast(list[Any], row.execution_state.get("messages", []))
                    for call in ModelMessage.model_validate(raw).tool_calls
                    if call.name == "workspace_execute"
                ]
                assert any(
                    "python" in str(call.arguments.get("command", "")).casefold()
                    for call in executed_calls
                ), "No actual Python command was attempted"
                assert observations.get("workspace_export"), "Report was not exported"
                attachments = list(answer.attachment_ids or [])
                assert attachments, "Final reply has no report attachment"
                found = False
                for identity in attachments:
                    artifact = await session.get(ArtifactRow, identity)
                    assert (
                        artifact is not None
                        and artifact.agent_id == agent_id
                        and artifact.thread_id == thread_id
                    )
                    path = confined_path(artifact_root, artifact.payload["key"])
                    content = path.read_bytes()
                    assert hashlib.sha256(content).hexdigest() == artifact.payload["sha256"]
                    if (
                        artifact.payload.get("name") == "calculation-report.txt"
                        and str(sum(value * value for value in range(1, 21))).encode() in content
                    ):
                        found = True
                assert found, "Report bytes did not contain the verified calculation"
        if journey == "topic_switch":
            followup_id = str(uuid4())
            run_ids.append(followup_id)
            async with db.sessions() as session, session.begin():
                thread = await session.get(ThreadRow, thread_id, with_for_update=True)
                assert thread is not None
                seq = thread.next_seq
                thread.next_seq += 1
                session.add(
                    MessageRow(
                        thread_id=thread_id,
                        agent_id=agent_id,
                        seq=seq,
                        role="user",
                        content=TOPIC_SWITCH_REQUEST,
                    )
                )
                session.add(
                    RunRow(
                        id=followup_id,
                        thread_id=thread_id,
                        agent_id=agent_id,
                        status="leased",
                        trigger="user",
                        prompt="",
                        input_seq=seq,
                        lease_owner=worker,
                        lease_fence=1,
                        lease_expires_at=utcnow() + timedelta(seconds=LEASE_SECONDS),
                        model_metadata={"acceptance_probe": True},
                    )
                )
            followup = replace(context, lease=Lease(run_id=followup_id, owner=worker, fence=1))
            contexts[followup_id] = followup
            async with asyncio.timeout(seconds):
                await execute_run(followup, registry, LEASE_SECONDS, maximum_rounds=16)
            async with db.sessions() as session:
                row = await session.get(RunRow, followup_id)
                assert row is not None
                assert row.status == "completed", "Topic-switch reply did not complete: " + str(
                    row.error_code or row.status
                )
                assert row.result and not public_reply_violation(row.result)
                observations = observe_results(row)
                working = [
                    ModelMessage.model_validate(item)
                    for item in row.execution_state.get("messages", [])
                ]
                latest_owner = next(
                    message.content
                    for message in reversed(working)
                    if message.role == "user" and message.context_origin == "conversation"
                )
                assert latest_owner == TOPIC_SWITCH_REQUEST, "Latest owner request was lost"
                numerals = row.result.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
                assert re.search(r"(?<!\d)56(?!\d)", numerals), (
                    "Latest arithmetic question was not answered"
                )
                answer = await session.scalar(
                    select(MessageRow)
                    .where(MessageRow.thread_id == thread_id, MessageRow.role == "assistant")
                    .order_by(MessageRow.seq.desc())
                    .limit(1)
                )
                assert answer is not None and answer.content == row.result
                summary = {
                    **summary,
                    "turns": 2,
                    "latest_owner_preserved": True,
                    "topic_switch_result": "PASS",
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "followup_operations": sorted(observations),
                }
                print(json.dumps(summary), flush=True)
        return summary
    finally:
        if created:
            async with db.sessions() as session, session.begin():
                receipts: list[str] = []
                for identity in run_ids:
                    row = await session.get(RunRow, identity)
                    calls = [
                        call
                        for raw in cast(
                            list[Any], row.execution_state.get("messages", []) if row else []
                        )
                        for call in ModelMessage.model_validate(raw).tool_calls
                    ]
                    receipts.extend(["outcome:" + identity, "outcome:" + identity + ":1"])
                    turn_context = contexts.get(identity)
                    if turn_context:
                        receipts.extend(
                            view_key(turn_context.for_call(call.id))
                            for call in calls
                            if call.name == "skill_view"
                        )
                await session.execute(
                    delete(EffectReceiptRow).where(EffectReceiptRow.key.in_(receipts))
                )
                await session.execute(
                    delete(EventRow).where(
                        or_(
                            EventRow.agent_id == agent_id,
                            EventRow.thread_id == thread_id,
                            EventRow.run_id.in_(run_ids),
                        )
                    )
                )
                await session.execute(
                    delete(AgentRow).where(AgentRow.id == agent_id, AgentRow.owner_id == owner_id)
                )
            async with db.sessions() as session:
                assert await session.get(AgentRow, agent_id) is None
                assert await session.get(ThreadRow, thread_id) is None
                for identity in run_ids:
                    assert await session.get(RunRow, identity) is None
                assert not await session.scalar(
                    select(func.count())
                    .select_from(EventRow)
                    .where(
                        or_(
                            EventRow.agent_id == agent_id,
                            EventRow.thread_id == thread_id,
                            EventRow.run_id.in_(run_ids),
                        )
                    )
                )
            print(json.dumps({"journey": journey, "cleanup": "PASS"}), flush=True)


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    db = Database.connect(settings.database_url)
    try:
        async with db.sessions() as session:
            owner_id = await session.scalar(select(OwnerRow.id))
        if not owner_id:
            print(json.dumps({"model_readiness": "unavailable", "reason": "owner_not_configured"}))
            assert args.check_model, "Acceptance needs an existing configured owner"
            return
        secrets = EncryptedSecretStore(db, settings.encryption_key.get_secret_value(), owner_id)
        credentials = ProviderCredentials(db, secrets)
        try:
            selection = select_model(await read_policy(db), Capability.CONVERSATION)
            configured = await credentials.configured(selection.provider)
            readiness = {
                "model_readiness": "ready" if configured else "unavailable",
                "provider": selection.provider,
                "model": selection.model,
                "credential_configured": configured,
                "workspace_socket_configured": bool(settings.workspace_socket),
            }
        except LonoraError as error:
            configured = False
            readiness = {"model_readiness": "unavailable", "reason": error.code}
        print(json.dumps(readiness), flush=True)
        if args.check_model:
            return
        assert configured, "Acceptance requires an already configured model credential"
        router = GlobalModelRouter(db, credentials)
        registry = AcceptanceRegistry()
        settings.artifact_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="acceptance-", dir=settings.artifact_root
        ) as directory:
            for journey in args.journey or JOURNEYS:
                if journey == "report":
                    assert settings.workspace_socket, (
                        "Report acceptance requires the configured workspace socket"
                    )
                await run_journey(
                    db,
                    owner_id,
                    router,
                    secrets,
                    registry,
                    Path(directory),
                    journey,
                    args.timeout,
                    args.evidence_dir,
                )
        print(
            json.dumps(
                {
                    "acceptance": "PASS",
                    "live_financial_capabilities": 0,
                    "broker_services": "denied",
                    "temporary_files": "removed",
                }
            )
        )
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow billable real provider requests; no live finance is enabled",
    )
    parser.add_argument(
        "--check-model", action="store_true", help="Check configuration without calling the model"
    )
    parser.add_argument("--journey", action="append", choices=list(JOURNEYS))
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Optionally save public nonfinancial visual replies for browser/native replay",
    )
    arguments = parser.parse_args()
    if not arguments.check_model and not arguments.allow_live_model:
        parser.error("--allow-live-model is required to make real model requests")
    if not 30 <= arguments.timeout <= 600:
        parser.error("--timeout must be between 30 and 600 seconds")
    asyncio.run(main(arguments))
