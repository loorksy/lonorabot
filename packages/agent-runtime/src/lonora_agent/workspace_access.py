"""Agent-owned durable files and fenced receipts on the existing Run lifecycle."""

import asyncio
import hashlib
from typing import Any, Protocol

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.runs import aware, require_lease
from lonora_db.schema import AnalyticalWorkspaceRow, RunRow, ThreadRow, WorkspaceOperationRow
from lonora_db.transactions import owned_agent
from lonora_session.idempotency import request_hash
from lonora_tools.context import ToolContext
from sqlalchemy.ext.asyncio import AsyncSession

from .workspace import WorkspaceResult, encode_snapshot, read_snapshot


class WorkspaceExecutor(Protocol):
    async def execute(
        self, command: str, files: dict[str, bytes] | None = None, *, deadline_seconds: float = 30
    ) -> WorkspaceResult: ...


async def scoped_run(
    session: AsyncSession, context: ToolContext, *, mutate: bool = False
) -> RunRow:
    agent = await owned_agent(session, context.owner_id, context.agent_id, lock=mutate)
    run = await require_lease(session, context.lease, lock=mutate)
    thread = await session.get(ThreadRow, run.thread_id)
    if (
        not context.call_id
        or run.agent_id != context.agent_id
        or run.thread_id != context.thread_id
        or thread is None
        or thread.owner_id != context.owner_id
    ):
        raise LonoraError("workspace_scope_mismatch", 409)
    if mutate and (
        agent.paused
        or run.trigger == "subagent"
        or run.model_metadata.get("authority") == "observe_only"
    ):
        raise LonoraError("tool_not_allowed", 403)
    return run


def manifest(revision: int, files: dict[str, bytes]) -> dict[str, Any]:
    return {
        "revision": revision,
        "files": [
            {"path": name, "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            for name, body in sorted(files.items())
        ],
    }


async def locked_workspace(session: AsyncSession, context: ToolContext) -> AnalyticalWorkspaceRow:
    await scoped_run(session, context, mutate=True)
    row = await session.get(AnalyticalWorkspaceRow, context.agent_id, with_for_update=True)
    if row is None:
        row = AnalyticalWorkspaceRow(agent_id=context.agent_id, revision=0, snapshot=b"{}")
        session.add(row)
        await session.flush()
    # An abandoned worker can never publish files after replacement: final
    # publication checks the current Run fence again, in the same transaction.
    if row.active_operation_id:
        operation = await session.get(WorkspaceOperationRow, row.active_operation_id)
        run = await session.get(RunRow, operation.run_id) if operation else None
        if (
            operation
            and operation.status == "running"
            and run
            and (
                run.status in {"leased", "running"}
                and run.lease_fence == operation.lease_fence
                and run.lease_expires_at is not None
                and aware(run.lease_expires_at) > utcnow()
            )
        ):
            return row
        if operation and operation.status == "running":
            operation.status = "abandoned"
            operation.result = {
                "ok": False,
                "code": "workspace_execution_interrupted",
                "operation_id": operation.id,
            }
            operation.updated_at = utcnow()
        row.active_operation_id = None
    return row


async def receipt(
    session: AsyncSession, context: ToolContext, digest: str
) -> dict[str, Any] | None:
    operation = await session.get(WorkspaceOperationRow, context.resource_id)
    if operation is None:
        return None
    if (
        operation.agent_id != context.agent_id
        or operation.run_id != context.lease.run_id
        or operation.request_hash != digest
    ):
        raise LonoraError("workspace_operation_conflict", 409)
    if operation.status == "running":
        raise LonoraError("workspace_busy", 409)
    return operation.result


def require_revision(row: AnalyticalWorkspaceRow, revision: int) -> None:
    if row.active_operation_id:
        raise LonoraError("workspace_busy", 409)
    if row.revision != revision:
        raise LonoraError("workspace_revision_conflict", 409)


class RunWorkspaceAccess:
    def __init__(self, executor: WorkspaceExecutor | None = None) -> None:
        self.executor = executor

    async def export(
        self, context: ToolContext, path: str, revision: int, name: str | None
    ) -> dict[str, Any]:
        from .workspace_artifacts import export_file

        return await export_file(context, path, revision, name)

    async def inspect(self, context: ToolContext) -> dict[str, Any]:
        async with context.db.sessions() as session, session.begin():
            await scoped_run(session, context)
            row = await session.get(AnalyticalWorkspaceRow, context.agent_id)
            active = (
                await session.get(WorkspaceOperationRow, row.active_operation_id)
                if row and row.active_operation_id
                else None
            )
            active_run = await session.get(RunRow, active.run_id) if active else None
            running = bool(
                active
                and active.status == "running"
                and active_run
                and active_run.status in {"leased", "running"}
                and active_run.lease_fence == active.lease_fence
                and active_run.lease_expires_at
                and aware(active_run.lease_expires_at) > utcnow()
            )
            return {
                **manifest(row.revision if row else 0, read_snapshot(row.snapshot) if row else {}),
                "execution_configured": self.executor is not None,
                "active_operation_id": row.active_operation_id if row and running else None,
                "recovery_required": bool(row and row.active_operation_id and not running),
            }

    async def read(
        self, context: ToolContext, path: str, revision: int, offset: int, limit: int
    ) -> dict[str, Any]:
        encode_snapshot({path: b""})
        if not 0 <= offset <= 2097152 or not 1 <= limit <= 16000:
            raise LonoraError("workspace_read_invalid", 422)
        async with context.db.sessions() as session, session.begin():
            await scoped_run(session, context)
            row = await session.get(AnalyticalWorkspaceRow, context.agent_id)
            if (row.revision if row else 0) != revision:
                raise LonoraError("workspace_revision_conflict", 409)
            files = read_snapshot(row.snapshot) if row else {}
            if path not in files:
                raise LonoraError("workspace_file_not_found", 404)
            try:
                content = files[path].decode("utf-8")
            except UnicodeError:
                raise LonoraError("workspace_file_binary", 422) from None
            return {
                "revision": revision,
                "path": path,
                "content": content[offset : offset + limit],
                "offset": offset,
                "next_offset": offset + limit if len(content) > offset + limit else None,
                "sha256": hashlib.sha256(files[path]).hexdigest(),
            }

    async def update(
        self, context: ToolContext, revision: int, files: dict[str, str], delete: list[str]
    ) -> dict[str, Any]:
        replacement = {path: body.encode("utf-8") for path, body in files.items()}
        encode_snapshot(replacement)
        encode_snapshot({path: b"" for path in delete})
        if set(files).intersection(delete):
            raise LonoraError("workspace_update_conflict", 422)
        digest = request_hash(
            {
                "kind": "workspace_update_v1",
                "revision": revision,
                "files": files,
                "delete": sorted(set(delete)),
            }
        )
        async with context.db.sessions() as session, session.begin():
            row = await locked_workspace(session, context)
            prior = await receipt(session, context, digest)
            if prior is not None:
                return prior
            require_revision(row, revision)
            snapshot = read_snapshot(row.snapshot)
            for path in delete:
                snapshot.pop(path, None)
            snapshot.update(replacement)
            row.snapshot = encode_snapshot(snapshot)
            row.revision += 1
            row.updated_at = utcnow()
            result = {"operation_id": context.resource_id, **manifest(row.revision, snapshot)}
            session.add(
                WorkspaceOperationRow(
                    id=context.resource_id,
                    agent_id=context.agent_id,
                    run_id=context.lease.run_id,
                    lease_fence=context.lease.fence,
                    request_hash=digest,
                    base_revision=revision,
                    status="completed",
                    result=result,
                )
            )
            return result

    async def execute(
        self, context: ToolContext, revision: int, command: str, deadline_seconds: int
    ) -> dict[str, Any]:
        if (
            not command.strip()
            or "\x00" in command
            or len(command.encode()) > 32768
            or not 1 <= deadline_seconds <= 45
        ):
            raise LonoraError("workspace_command_invalid", 422)
        digest = request_hash(
            {
                "kind": "workspace_execute_v1",
                "revision": revision,
                "command": command,
                "deadline_seconds": deadline_seconds,
            }
        )
        async with context.db.sessions() as session, session.begin():
            row = await locked_workspace(session, context)
            prior = await receipt(session, context, digest)
            if prior is not None:
                return prior
            require_revision(row, revision)
            if self.executor is None:
                raise LonoraError("workspace_execution_unconfigured", 409)
            snapshot = read_snapshot(row.snapshot)
            row.active_operation_id = context.resource_id
            session.add(
                WorkspaceOperationRow(
                    id=context.resource_id,
                    agent_id=context.agent_id,
                    run_id=context.lease.run_id,
                    lease_fence=context.lease.fence,
                    request_hash=digest,
                    base_revision=revision,
                    status="running",
                    result={},
                )
            )
        # No DB lock is held across container execution or IPC.
        try:
            outcome = await self.executor.execute(
                command, snapshot, deadline_seconds=deadline_seconds
            )
            encoded = encode_snapshot(outcome.files)
            async with context.db.sessions() as session, session.begin():
                row = await locked_workspace(session, context)
                if row.active_operation_id != context.resource_id or row.revision != revision:
                    raise LonoraError("workspace_operation_superseded", 409)
                operation = await session.get(WorkspaceOperationRow, context.resource_id)
                if (
                    operation is None
                    or operation.lease_fence != context.lease.fence
                    or operation.status != "running"
                ):
                    raise LonoraError("workspace_operation_superseded", 409)
                row.snapshot, row.active_operation_id = encoded, None
                row.revision += 1
                row.updated_at = utcnow()
                result = {
                    "operation_id": context.resource_id,
                    "exit_code": outcome.exit_code,
                    "stdout": outcome.stdout,
                    "stderr": outcome.stderr,
                    "image": outcome.image,
                    **manifest(row.revision, outcome.files),
                }
                operation.status, operation.result, operation.updated_at = (
                    "completed",
                    result,
                    utcnow(),
                )
                return result
        except BaseException as error:
            code = (
                error.code if isinstance(error, LonoraError) else "workspace_execution_interrupted"
            )
            cleanup = asyncio.create_task(self._abort(context, code))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise
            raise

    async def _abort(self, context: ToolContext, code: str) -> None:
        # May run after lease expiry. It may settle only this exact operation;
        # it cannot publish a snapshot, advance a revision or release newer work.
        async with context.db.sessions() as session, session.begin():
            try:
                await owned_agent(session, context.owner_id, context.agent_id, lock=True)
            except LonoraError as error:
                if error.code == "agent_not_found":
                    return  # Owner deletion already cascaded the workspace/receipt.
                raise
            row = await session.get(AnalyticalWorkspaceRow, context.agent_id, with_for_update=True)
            operation = await session.get(WorkspaceOperationRow, context.resource_id)
            if (
                operation
                and operation.status == "running"
                and operation.run_id == context.lease.run_id
                and operation.lease_fence == context.lease.fence
            ):
                operation.status = "failed"
                operation.result = {"ok": False, "code": code, "operation_id": operation.id}
                operation.updated_at = utcnow()
                if row and row.active_operation_id == operation.id:
                    row.active_operation_id = None
