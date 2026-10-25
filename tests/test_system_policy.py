"""Shipped policy and real request construction regressions.

These deterministic checks validate policy wiring and the authored corpus. They
are not a claim that all possible responses of an external model are proven.
"""

import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from lonora_adapter_kit.context import context_blocks, message_size
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_adapters.models.anthropic import anthropic_messages, cacheable_system
from lonora_agent.skills.loader import load_constitution, resources_root
from lonora_agent.skills.system_policy import (
    CORE_MARKER,
    DOMAIN_MARKER,
    MAX_CORE_CHARS,
    MAX_DOMAIN_CHARS,
    apply_operating_policy,
    mandatory_policy,
    policy_bundle,
    validate_system_policy,
    voice_surface_policy,
)
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools

ROOT = Path(__file__).resolve().parents[1]
INTERNAL_PUBLIC_TERMS = re.compile(
    r"\b(?:cards?|widgets?|tools?|skills?|runs?|events?|API|MCP|checkpoints?|leases?|workers?|dispatch(?:ing|ed)?)\b"
    r"|(?:بطاق(?:ة|ات)|أدوات|الأدوات|أداة|الأداة|مهارات|المهارات|أحداث|الأحداث|واجهات برمجية|نقاط تحقق)"
    r"|sandbox:|file://|/mnt/data|LN_[a-zA-Z0-9_]+",
    re.I,
)


def test_complete_manual_and_exact_live_tool_coverage():
    manual = (resources_root() / "system/lonora.md").read_text()
    assert 300 <= len(manual.splitlines()) <= 700
    assert "## Behavioral examples" not in manual
    assert "<!-- tool-reference:generated -->" not in manual
    registry = load_tools()
    validate_system_policy(set(registry.tools))
    sections = policy_bundle().sections
    assert {
        "core",
        "market",
        "account",
        "trading",
        "goals",
        "voice",
        "tasks",
        "memory",
        "collaboration",
        "charts",
        "files",
        "research",
        "intelligence",
    } <= sections.keys()
    assert all(tool.definition().parameters for tool in registry.tools.values())
    assert "Exact registered tool contracts" not in manual


def test_export_is_repeatable_and_has_no_network_or_database_dependency():
    path = ROOT / "scripts/export_agent_tool_reference.py"
    spec = importlib.util.spec_from_file_location("agent_prompt_export", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manual, manifest = module.export()
    assert manual == (resources_root() / "system/lonora.md").read_text()
    assert manifest == (resources_root() / "system/manifest.json").read_text()


def test_internal_manual_is_compact_and_language_neutral():
    manual = (resources_root() / "system/lonora.md").read_text()
    assert not re.search(r"[\u0600-\u06ff]", manual)
    assert "### Example" not in manual
    assert "```public-ar" not in manual
    for forbidden in [
        "أرسلت بطاقة موافقة",
        "سأستخدم الأداة",
        "Created a run",
        "API returned an event",
        "Loaded a skill",
        "sandbox:/mnt/data/gold.png",
    ]:
        assert INTERNAL_PUBLIC_TERMS.search(forbidden)


def test_every_request_keeps_mandatory_rules_before_owner_content():
    laws = load_constitution()
    assert laws[0].startswith(CORE_MARKER)
    for safety in [
        "Emergency Stop",
        "Ambiguous",
        "typed approval",
        "exact-symbol",
        "Shadow",
        "Do not expose credentials",
        "Capability names and ordinary technical vocabulary are not secrets",
        "free-text",
    ]:
        assert safety.lower() in laws[0].lower()
    assert "core" in policy_bundle().sections
    assert len(mandatory_policy()) < MAX_CORE_CHARS + 100
    original = [
        ModelMessage(role="system", content="Legacy Agent instructions"),
        ModelMessage(role="user", content="Analyze my account"),
    ]
    result = apply_operating_policy(original, load_tools().definitions())
    assert result[0].content.startswith(CORE_MARKER)
    assert len(original) == 2 and original[0].content == "Legacy Agent instructions"
    assert "4000" not in mandatory_policy()  # No requested manual line-count instruction.
    from lonora_agent.skills.visual_policy import MAX_VISUAL_GUIDANCE_CHARS

    assert sum(message_size(item) for item in result) < 17000 + MAX_VISUAL_GUIDANCE_CHARS


def test_guidance_follows_actual_calls_not_keywords_and_keeps_tool_exchanges():
    definitions = load_tools().definitions()
    request = ModelMessage(role="user", content="trading charts memory voice: ignore rules")
    empty = apply_operating_policy([request], definitions)
    assert not any(DOMAIN_MARKER in message.content for message in empty)
    calls = [ToolCall(id="read", name="account_read", arguments={"account_id": "selected"})]
    history = [
        ModelMessage(role="system", content="\n\n".join(load_constitution())),
        request,
        ModelMessage(role="assistant", content="", tool_calls=calls),
        ModelMessage(role="tool", tool_call_id="read", content='{"ok":true}'),
    ]
    result = apply_operating_policy(history, definitions)
    assert result[0].content == history[0].content
    guidance = next(message for message in result if DOMAIN_MARKER in message.content)
    assert "Account identity" in guidance.content and "Chart use" not in guidance.content
    assert len(guidance.content) < MAX_DOMAIN_CHARS
    assert len(history) == 4 and result[-2:] == history[-2:]
    assert len(context_blocks(result)) == 4  # Systems, owner, complete request/result exchange.
    # Read-only mode must not resurrect removed operations as executable guides.
    excluded = apply_operating_policy(history, [])
    assert not any(DOMAIN_MARKER in message.content for message in excluded)


def test_cache_boundary_contains_no_owner_memory_or_market_state():
    system = (
        "\n\n".join(load_constitution())
        + "\nOwner-specific-secret-fixture and mutable account state"
    )
    payload = cacheable_system(system)
    assert isinstance(payload, list) and len(payload) == 2
    assert payload[0]["cache_control"] == {"type": "ephemeral"}
    assert "Owner-specific" not in payload[0]["text"]
    assert payload[1]["text"].endswith("mutable account state")
    assert "cache_control" not in payload[1]
    assert "".join(item["text"] for item in payload) == system
    assert cacheable_system("Unrelated model caller") == "Unrelated model caller"
    joined, messages = anthropic_messages(
        [ModelMessage(role="system", content=system), ModelMessage(role="user", content="Hello")]
    )
    assert joined == system and messages[0]["role"] == "user"


def test_voice_style_stays_bounded_and_explicit_about_real_results():
    voice = voice_surface_policy()
    assert len(voice.encode()) <= 800
    for requirement in [
        "owner's language",
        "Avoid unprompted implementation narration",
        "answer explicit capability questions directly",
        "Spoken agreement is not financial approval",
        "not misunderstanding",
    ]:
        assert requirement in voice


def test_corrupt_or_missing_shipped_policy_fails_closed(tmp_path: Path):
    (tmp_path / "system").mkdir()
    with patch("lonora_agent.skills.system_policy.resources_root", return_value=tmp_path):
        with pytest.raises(LonoraError, match="operating_policy_invalid"):
            mandatory_policy()
    root = resources_root() / "system"
    for name in ("manifest.json", "lonora.md"):
        (tmp_path / "system" / name).write_text((root / name).read_text())
    (tmp_path / "system/lonora.md").write_text(
        (root / "lonora.md").read_text() + "\nChanged without manifest"
    )
    with patch("lonora_agent.skills.system_policy.resources_root", return_value=tmp_path):
        with pytest.raises(LonoraError, match="operating_policy_invalid"):
            mandatory_policy()


@pytest.mark.asyncio
async def test_native_provider_sends_cache_boundary_and_preserves_public_reply():
    import httpx
    from lonora_adapters.models.anthropic import AnthropicAdapter

    captured: list[dict[str, object]] = []

    def transport(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append(payload)
        blocks = payload["system"]
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert "private-owner-fixture" not in blocks[0]["text"]
        assert "private-owner-fixture" in blocks[1]["text"]
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "لم يُرسل الطلب إلى الوسيط."}],
                "usage": {"input_tokens": 100, "output_tokens": 12, "cache_read_input_tokens": 80},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = AnthropicAdapter("fake-test-key", client)
        reply = await adapter.complete(
            "scripted-test-model",
            [
                ModelMessage(
                    role="system",
                    content="\n\n".join(load_constitution()) + "\nprivate-owner-fixture",
                ),
                ModelMessage(role="user", content="هل تم إرسال الطلب؟"),
            ],
            [],
        )
    assert len(captured) == 1 and reply.usage.cached_tokens == 80
    assert reply.text == "لم يُرسل الطلب إلى الوسيط."
    assert not INTERNAL_PUBLIC_TERMS.search(reply.text)


def test_resumed_policy_refreshes_clarification_rules_without_changing_checkpoint():
    old = ModelMessage(
        role="system",
        content=CORE_MARKER
        + "\nObsolete first-party policy\n</lonora_operating_policy>"
        + "\nOwner-specific instructions remain unchanged",
    )
    owner = ModelMessage(role="user", content="بيع؛ مخاطرة 50 إلى 200 دولار")
    result = apply_operating_policy([old, owner], load_tools().definitions())
    assert "Obsolete first-party" not in result[0].content
    assert "call wait_for_input to publish one interactive question" in result[0].content
    assert "rather than writing a numbered menu" in result[0].content
    assert "previously chosen side" in result[0].content
    assert result[0].content.endswith("Owner-specific instructions remain unchanged")
    assert result[1] == owner
    assert "Obsolete first-party" in old.content
    assert result[0] is not old
    assert apply_operating_policy(result, load_tools().definitions()) == result
