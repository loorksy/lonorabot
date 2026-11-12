"""The head swap of a waking Run: what is replaced and what is kept exactly."""

from types import SimpleNamespace
from typing import Any

import pytest
from lonora_adapter_kit.context import omission_notice
from lonora_adapter_kit.context_sections import ContextSection, context_message
from lonora_adapter_kit.types import ModelMessage
from lonora_agent import loop_restore


def data(text: str) -> ModelMessage:
    message = context_message([ContextSection("memory", "agent_memory", "agent_authored", text)])
    assert message is not None
    return message


TRANSCRIPT = [
    ModelMessage(role="user", content="Manage the book"),
    ModelMessage(role="assistant", content="Waiting for the timer."),
    # A history-omission notice belongs to the transcript, never to the head.
    omission_notice(3, 1),
]


async def swap(
    monkeypatch: pytest.MonkeyPatch, old: list[ModelMessage], fresh: list[ModelMessage]
) -> list[ModelMessage]:
    async def build(*_: Any) -> list[ModelMessage]:
        return fresh

    async def skills(*_: Any, **__: Any) -> list[str]:
        return []

    monkeypatch.setattr(loop_restore, "build_context", build)
    monkeypatch.setattr(loop_restore, "refresh_skill_context", skills)
    messages = list(old)
    context: Any = SimpleNamespace()
    await loop_restore.refresh_context_head(context, Any, {}, messages)  # type: ignore[arg-type]
    return messages


@pytest.mark.asyncio
async def test_the_fresh_head_replaces_the_old_and_the_transcript_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_notice = omission_notice(0, 0, guidance=["lonora_recorded_decisions"])
    old = [
        ModelMessage(role="system", content="old policy"),
        ModelMessage(role="system", content="old routing"),
        data("old memory"),
        old_notice,
        *TRANSCRIPT,
    ]
    fresh_notice = omission_notice(0, 0, guidance=["lonora_operational_observations"])
    fresh = [
        ModelMessage(role="system", content="new policy"),
        ModelMessage(role="system", content="new picture"),
        data("new memory"),
        fresh_notice,
        ModelMessage(role="user", content="history the fresh build read"),
    ]
    assert await swap(monkeypatch, old, fresh) == [*fresh[:4], *TRANSCRIPT]


@pytest.mark.asyncio
async def test_a_guidance_notice_comes_and_goes_with_the_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notice = omission_notice(0, 0, guidance=["lonora_recorded_decisions"])
    with_notice = [ModelMessage(role="system", content="policy"), data("memory"), notice]
    without = [ModelMessage(role="system", content="policy"), data("memory")]
    # The fresh build shed guidance: its notice says so.
    assert await swap(monkeypatch, [*without, *TRANSCRIPT], with_notice) == [
        *with_notice,
        *TRANSCRIPT,
    ]
    # The fresh build shed nothing: the old notice no longer holds and goes.
    assert await swap(monkeypatch, [*with_notice, *TRANSCRIPT], without) == [
        *without,
        *TRANSCRIPT,
    ]
