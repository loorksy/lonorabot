"""The run copy of an enabled package version: skills/<id>/<version>/ in the agent's home,
where its utilities run (7.1). Validation and activation write it fresh; a version enabled
before the package store existed, or whose copy is gone, gets it here, from the store,
once per Gateway start."""

import shlex

from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import SkillRow
from lonora_security.secrets import SecretScan
from lonora_workspace.client import WorkspaceClient
from sqlalchemy import select

from .store import stored_files, version_paths

PER_TICK = 10
Checked = set[tuple[str, str, str]]


async def write_copy(
    workspace: WorkspaceClient,
    scan: SecretScan,
    agent_id: str,
    directory: str,
    files: dict[str, bytes],
) -> None:
    """Replace `directory` in the agent's home with exactly `files` (paths under it)."""
    cleared = await workspace.run(
        scan, agent_id, "rm -rf -- " + shlex.quote(directory), timeout_seconds=60
    )
    if cleared.get("exit_code") != 0:
        raise LonoraError("workspace_file_unwritable", 409)
    for path, data in sorted(files.items()):
        if not (await workspace.write(scan, agent_id, path, data))["ok"]:
            raise LonoraError("workspace_file_unwritable", 409)


async def restore_run_copies(db: Database, workspace: WorkspaceClient, checked: Checked) -> int:
    """Write the missing run copies of up to PER_TICK enabled versions not checked since
    the Gateway started; returns how many were written. A present copy is left as the agent
    has it. Only acknowledgements and an exit status come back: there is nothing to scan."""
    async with db.sessions() as session:
        rows = (await session.scalars(select(SkillRow).where(SkillRow.agent_id.is_not(None)))).all()
        wanted = [
            (str(row.agent_id), str(row.payload["name"]), str(row.payload["manifest"]["version"]))
            for row in rows
            if "package" in row.state
            and row.payload.get("enabled")
            and isinstance(row.payload.get("manifest"), dict)
            and row.payload["manifest"].get("version")
        ]
    pending = [item for item in wanted if item not in checked][:PER_TICK]
    written, scan = 0, SecretScan({})
    for agent_id, name, version in pending:
        directory = f"skills/{name}/{version}"
        present = await workspace.run(
            scan, agent_id, "test -f " + shlex.quote(directory + "/SKILL.md"), timeout_seconds=30
        )
        if present.get("exit_code") != 0:
            async with db.sessions() as session:
                paths = await version_paths(session, agent_id, directory)
                files = await stored_files(session, agent_id, paths)
            if files:
                await write_copy(workspace, scan, agent_id, directory, files)
                written += 1
        checked.add((agent_id, name, version))
    return written
