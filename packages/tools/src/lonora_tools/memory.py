from typing import Any, Literal, Self

from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_db.memory import memory_data, memory_provenance, read_memory
from lonora_memory.commit import atomic_commit, atomic_edit
from lonora_memory.edits import MemoryEdit, MemoryEditError, MemoryOverflow
from lonora_memory.profile import profile_documents
from pydantic import Field, model_validator

from .base import Tool, eager_for
from .context import ToolContext


class Empty(Contract):
    """No arguments are needed: memory is bound to the current persistent agent."""


class MemoryOperation(Contract):
    action: Literal["add", "patch", "remove"]
    section: Literal["USER.md", "MEMORY.md"] = "MEMORY.md"
    content: str = Field(default="", max_length=8000)
    old_text: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def required_text(self) -> Self:
        if self.action == "add" and not self.content.strip():
            raise ValueError("memory_edit_content_required")
        if self.action != "add" and not self.old_text.strip():
            raise ValueError("memory_edit_old_text_required")
        return self


class MemoryWrite(Contract):
    version: int = Field(ge=1)
    content: str | None = Field(default=None, max_length=30000)
    operations: list[MemoryOperation] = Field(default_factory=list[MemoryOperation], max_length=20)

    @model_validator(mode="after")
    def one_shape(self) -> Self:
        if (self.content is None) == (not self.operations):
            raise ValueError("memory_write_shape_invalid")
        return self


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        row = await read_memory(session, context.owner_id, context.agent_id)
        return {
            **memory_data(row),
            "document_sections": list(profile_documents(row.content)),
            "provenance": await memory_provenance(session, row.agent_id, row.version),
        }


async def write(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not args.get("operations"):
        return await atomic_commit(
            context.db,
            context.owner_id,
            context.agent_id,
            args["content"],
            args["version"],
            lease=context.lease,
            effect_key=context.effect_key,
        )
    edits = [MemoryEdit(**item) for item in args["operations"]]
    try:
        return await atomic_edit(
            context.db,
            context.owner_id,
            context.agent_id,
            edits,
            args["version"],
            lease=context.lease,
            effect_key=context.effect_key,
        )
    except (MemoryEditError, MemoryOverflow) as error:
        # Nothing was saved; the details let the model correct one batch.
        return error.result()
    except LonoraError as error:
        if error.code != "version_conflict":
            raise
        async with context.db.sessions() as session:
            current = await read_memory(session, context.owner_id, context.agent_id)
        # Operations are content-addressed, so a batch can be re-checked against
        # the newer revision without resending or re-reading the whole document.
        return {
            "ok": False,
            "code": "version_conflict",
            "version": current.version,
            "chars": len(current.content),
        }


def tools() -> list[Tool]:
    return [
        Tool(
            "memory_read",
            "Read this Agent's durable USER.md/preferences and memory/MEMORY.md views with their shared revision. Old unsectioned content stays long-term memory. Past conversations are searchable with session_search.",
            Empty,
            read,
            True,
            eager=eager_for("core"),
        ),
        Tool(
            "memory_write",
            "Change durable memory atomically at its current revision. operations apply in "
            "order, all or nothing: add appends content to USER.md (owner preferences) or "
            "MEMORY.md (knowledge); patch replaces old_text, unique in the document, with "
            "content; remove deletes the lines old_text touches. An add equal to an existing entry "
            "returns changed false. The 30000-char limit applies to the result; overflow returns "
            "the shortfall. content replaces the whole document. No "
            "credentials or live prices; preferences grant no financial authority. Say "
            "remembered only after success.",
            MemoryWrite,
            write,
            replay_safe=True,
            eager=eager_for("core"),
        ),
    ]
