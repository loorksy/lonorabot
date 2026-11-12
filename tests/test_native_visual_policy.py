"""The generative-UI block of the system prompt; no provider or database required."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from lonora_adapter_kit.types import ModelMessage
from lonora_adapters.models.anthropic import cacheable_system
from lonora_agent.genui_vocabulary import genui_vocabulary
from lonora_agent.skills.loader import load_constitution, resources_root
from lonora_agent.skills.system_policy import (
    MAX_CORE_CHARS,
    apply_operating_policy,
    mandatory_policy,
)
from lonora_agent.skills.visual_policy import (
    MAX_GENUI_GUIDANCE_CHARS,
    VISUAL_END,
    VISUAL_MARKER,
    native_visual_policy,
)
from lonora_core.user_error import LonoraError
from test_system_policy import unseeded


def test_compact_vocabulary_is_loaded_before_mutable_owner_context():
    core = mandatory_policy()
    vocabulary = native_visual_policy()
    assert len(core) <= MAX_CORE_CHARS + 100
    assert len(vocabulary) <= MAX_GENUI_GUIDANCE_CHARS
    prefix = load_constitution()[0]
    assert prefix == core + "\n\n" + vocabulary
    assert vocabulary.count(VISUAL_MARKER) == 1
    # v2 is the only generative-UI teaching (mandate 10.1.3): the generated vocabulary of
    # the contract, never the v1 document grammar.
    assert "<lonora_generative_ui>" in vocabulary and genui_vocabulary() in vocabulary
    assert '{"version"' not in vocabulary and "lonora-design" not in vocabulary
    assert "{teaching}" not in vocabulary and "<!--" not in vocabulary


def test_ordinary_and_resumed_requests_keep_single_current_vocabulary():
    owner = ModelMessage(role="user", content="Explain equity simply.")
    old = ModelMessage(
        role="system",
        content=mandatory_policy()
        + "\n\n"
        + VISUAL_MARKER
        + "obsolete grammar"
        + VISUAL_END
        + "\nOwner preferences remain intact",
    )
    tools = unseeded()
    current = apply_operating_policy([old, owner], tools)
    assert "obsolete grammar" not in current[0].content
    assert "obsolete grammar" in old.content
    assert current[0].content.count(VISUAL_MARKER) == 1
    assert current[0].content.endswith("Owner preferences remain intact")
    assert current[1:] == [owner]
    assert apply_operating_policy(current, tools) == current
    plain = apply_operating_policy([owner], tools)
    assert native_visual_policy() in plain[0].content
    assert plain[-1] == owner


def test_cache_boundary_contains_visual_grammar_but_no_owner_material():
    prefix = load_constitution()[0]
    source = prefix + "\nOwner-specific-account-observation"
    payload = cacheable_system(source)
    assert isinstance(payload, list)
    assert payload[0]["text"] == prefix
    assert payload[0]["cache_control"] == {"type": "ephemeral"}
    assert payload[1]["text"] == "\nOwner-specific-account-observation"
    assert "cache_control" not in payload[1]
    # The adapter must not search past mutable content for another marker.
    separated = mandatory_policy() + "\nOwner content\n" + native_visual_policy()
    blocks = cacheable_system(separated)
    assert isinstance(blocks, list)
    assert blocks[0]["text"] == mandatory_policy()
    assert "Owner content" in blocks[1]["text"]


def test_missing_or_oversized_vocabulary_is_an_explicit_resource_error(tmp_path: Path):
    with patch("lonora_agent.skills.visual_policy.resources_root", return_value=tmp_path):
        with pytest.raises(LonoraError, match="visual_policy_invalid"):
            native_visual_policy()
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts/genui_v2_teaching.md").write_text("")
        path = tmp_path / "prompts/genui_v2.md"
        path.write_text(VISUAL_MARKER + "x" * MAX_GENUI_GUIDANCE_CHARS + VISUAL_END)
        with pytest.raises(LonoraError, match="visual_policy_invalid"):
            native_visual_policy()
    assert resources_root().is_dir()


def test_the_teaching_names_only_what_the_catalog_builds():
    text = native_visual_policy()
    for gone in ("(picker)", "(checklist)", "(chart)", "(quiz)", "(timer)"):
        assert gone not in text
    assert not re.search("[\u0600-\u06ff]", text[: text.index("Instrument names")])
