"""The owner-control fingerprint of ``lonora update`` (infra/compose/lonora-controls.sh).

A release that drops a table must never make the owner-control records unreadable: the
update would roll back ("reading the owner-control records") although nothing is wrong.
The fingerprint is read with the target release's definition on both sides, every part
is guarded with ``to_regclass``, and it still changes when an owner control changes.

The fingerprint runs in bash with ``psql`` against a disposable PostgreSQL database
(``LONORA_TASK_TEST_DATABASE_URL``), in two hand-made schemas (one holding every table it
reads, one where a release dropped some) and in the migrated schema itself.
"""

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ROOT / "infra/compose/lonora-controls.sh"
LONORA = ROOT / "infra/compose/lonora"
URL = os.environ.get("LONORA_TASK_TEST_DATABASE_URL", "")

postgres = pytest.mark.skipif(
    not URL or shutil.which("psql") is None,
    reason="needs psql and LONORA_TASK_TEST_DATABASE_URL (a disposable *_test database)",
)

# psql_value as infra/compose/lonora defines it, against the test database.
PSQL_VALUE = (
    'psql_value() { psql "$DSN" -v ON_ERROR_STOP=1 -tAc "$1" 2>/dev/null | tr -d \'[:space:]\'; }'
)

TABLES = {
    "ln_trading_restrictions": "id text, v text",
    "ln_account_authorities": "id text, v text",
    "ln_supervision_holds": "id text, v text",
    "ln_owner_actions": "id text, v text",
    "ln_trade_approvals": "id text, v text",
    "ln_trading_journal": "id text, v text",
    "ln_settings": "key text, payload json",
    "ln_agents": "id text, paused boolean",
    "ln_broker_sessions": "id text, payload json",
    "ln_tickets": "id text, state json",
    "ln_messages": "id text, role text, content text",
}


def dsn() -> str:
    return URL.replace("postgresql+asyncpg://", "postgresql://", 1)


def sql(statement: str, schema: str | None = None) -> None:
    options = {"PGOPTIONS": f"-c search_path={schema}"} if schema else {}
    subprocess.run(
        ["psql", dsn(), "-v", "ON_ERROR_STOP=1", "-qc", statement],
        check=True,
        capture_output=True,
        env={**os.environ, **options},
    )


def fingerprint(schema: str | None = None, definition: Path = CONTROLS) -> str:
    env = {**os.environ, "DSN": dsn()}
    if schema:
        env["PGOPTIONS"] = f"-c search_path={schema}"
    script = f"set -euo pipefail; {PSQL_VALUE}; source '{definition}'; control_fingerprint"
    result = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def schemas() -> Iterator[tuple[str, str]]:
    """Two schemas: every table the fingerprint reads, and one a release dropped some of."""
    full, dropped = "fp_full_" + uuid4().hex[:8], "fp_dropped_" + uuid4().hex[:8]
    sql(f"CREATE SCHEMA {full}; CREATE SCHEMA {dropped}")
    for name, columns in TABLES.items():
        sql(f"CREATE TABLE {full}.{name} ({columns})")
        if name not in {"ln_settings", "ln_supervision_holds"}:
            sql(f"CREATE TABLE {dropped}.{name} ({columns})")
    sql(
        f"""INSERT INTO {full}.ln_trading_restrictions VALUES ('r1', 'no_new_entries');
        INSERT INTO {full}.ln_settings VALUES ('trading_control', '{{"enabled": true}}');
        INSERT INTO {full}.ln_settings VALUES ('ui_theme', '{{"dark": true}}');
        INSERT INTO {full}.ln_agents VALUES ('a1', false);
        INSERT INTO {full}.ln_broker_sessions VALUES ('c1', '{{"enabled": true}}');
        INSERT INTO {full}.ln_messages VALUES ('m1', 'user', 'hello');
        INSERT INTO {full}.ln_messages VALUES ('m2', 'assistant', 'hi');
        INSERT INTO {full}.ln_tickets VALUES ('k1', '{{"task": {{"status": "running"}}}}')"""
    )
    try:
        yield full, dropped
    finally:
        sql(f"DROP SCHEMA {full} CASCADE; DROP SCHEMA {dropped} CASCADE")


@postgres
def test_a_dropped_table_never_makes_the_records_unreadable(schemas: tuple[str, str]) -> None:
    full, dropped = schemas
    whole, without = fingerprint(full), fingerprint(dropped)
    assert len(whole) == 64 and len(without) == 64
    assert whole == fingerprint(full)
    assert whole != without


@postgres
@pytest.mark.parametrize(
    "change",
    [
        "UPDATE ln_trading_restrictions SET v = 'revoked'",
        "INSERT INTO ln_supervision_holds VALUES ('h1', 'owner')",
        "UPDATE ln_agents SET paused = true",
        "UPDATE ln_broker_sessions SET payload = '{\"enabled\": false}'",
        "UPDATE ln_settings SET payload = '{\"enabled\": false}' WHERE key = 'trading_control'",
        "INSERT INTO ln_trade_approvals VALUES ('t1', 'pending')",
        "INSERT INTO ln_messages VALUES ('m3', 'user', 'close everything')",
        # A Task's state is nested under "task" (lonora_db.tasks).
        'UPDATE ln_tickets SET state = \'{"task": {"status": "paused"}}\'',
        'UPDATE ln_tickets SET state = \'{"task": {"status": "running", '
        '"control_requested": "cancel"}}\'',
    ],
)
def test_an_owner_control_change_changes_the_fingerprint(
    schemas: tuple[str, str], change: str
) -> None:
    full, _ = schemas
    before = fingerprint(full)
    sql(change, full)
    assert fingerprint(full) != before


@postgres
def test_records_that_are_not_controls_leave_it_unchanged(schemas: tuple[str, str]) -> None:
    full, _ = schemas
    before = fingerprint(full)
    sql(
        """UPDATE ln_settings SET payload = '{"dark": false}' WHERE key = 'ui_theme';
        INSERT INTO ln_messages VALUES ('m4', 'assistant', 'done')""",
        full,
    )
    assert fingerprint(full) == before


@postgres
def test_the_migrated_schema_is_readable() -> None:
    # Every table of the definition the migrated schema has is read, not skipped as absent.
    missing = subprocess.run(
        ["psql", dsn(), "-tAc", "SELECT count(*) FROM pg_tables WHERE tablename = 'ln_agents'"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert missing.stdout.strip() == "1", "the test database is not migrated"
    assert len(fingerprint()) == 64


@postgres
def test_an_unreadable_database_gives_no_fingerprint(tmp_path: Path) -> None:
    env = {**os.environ, "DSN": "postgresql://nobody@127.0.0.1:1/none"}
    script = f"set -euo pipefail; {PSQL_VALUE}; source '{CONTROLS}'; control_fingerprint"
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == ""


def lonora_functions(home: Path, body: str) -> subprocess.CompletedProcess[str]:
    """Run ``body`` with the functions of infra/compose/lonora loaded, inside ``home``."""
    text = LONORA.read_text()
    source = text[: text.rindex('\nmain "$@"')] + "\n"
    script = home / "lonora-functions.sh"
    script.write_text(source)
    return subprocess.run(
        ["bash", "-c", f"source '{script}'; cd '{home}'; {body}"],
        env={**os.environ, "LONORA_HOME": str(home)},
        capture_output=True,
        text=True,
    )


def test_an_unfinished_update_reads_with_its_target_definition(tmp_path: Path) -> None:
    (tmp_path / "infra/compose").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    installed = tmp_path / "infra/compose/lonora-controls.sh"
    installed.write_text("control_fingerprint() { echo installed; }\n")
    target = tmp_path / "state/update-controls.sh"
    target.write_text("control_fingerprint() { echo target; }\n")
    result = lonora_functions(tmp_path, "use_controls && control_fingerprint")
    assert result.stdout.strip() == "target", result.stderr
    target.unlink()
    result = lonora_functions(tmp_path, "use_controls && control_fingerprint")
    assert result.stdout.strip() == "installed", result.stderr


def test_a_target_without_its_own_definition_uses_the_installed_one(tmp_path: Path) -> None:
    (tmp_path / "infra/compose").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    (tmp_path / "infra/compose/lonora-controls.sh").write_text("# installed\n")
    # An image built before the definition was its own file: cat finds nothing.
    result = lonora_functions(
        tmp_path,
        "image_file() { return 1; }; target_controls old-image state/out.sh && cat state/out.sh",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith("# installed\n")
    assert "carries no owner-control definition" in result.stdout
    result = lonora_functions(
        tmp_path,
        "image_file() { echo '# target'; }; target_controls new-image state/out.sh && cat state/out.sh",
    )
    assert result.stdout.strip() == "# target", result.stderr


def test_the_installed_definition_is_the_one_the_image_ships() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY infra/compose ./deploy/infra/compose" in dockerfile
    assert CONTROLS.is_file()


def test_the_update_continues_with_the_target_releases_own_lonora(tmp_path: Path) -> None:
    """The running (old) script hands the update to the target's copy before any change."""
    (tmp_path / "state").mkdir()
    target = (
        '#!/usr/bin/env bash\necho "target lonora $* home=$LONORA_HOME tool=$LONORA_TARGET_TOOL"\n'
    )
    # The block of cmd_update under test, taken from the script itself.
    block = f"sed -n '/# The update runs as the target release/,/^    local controls=/p' '{LONORA}'"
    script = (
        "set -euo pipefail; keep_data=true; pinned=repo@sha256:abc; "
        "SELF=/nonexistent/lonora; CMD_NAME=lonora; STATE=state; "
        'say() { echo "say: $*"; }; image_file() { printf "%s" "$TARGET"; }; '
        f"eval \"step() {{ $({block} | sed '$d'); }}\"; step"
    )

    def run(**extra: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "TARGET": target, "LONORA_HOME": str(tmp_path), **extra}
        return subprocess.run(
            ["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
        )

    handed = run()
    assert handed.returncode == 0, handed.stderr
    assert "target lonora update repo@sha256:abc --keep-data" in handed.stdout, handed.stdout
    assert "tool=1" in handed.stdout and f"home={tmp_path}" in handed.stdout
    # Already the target's own copy: it is not run again.
    again = run(LONORA_TARGET_TOOL="1")
    assert again.returncode == 0 and "target lonora" not in again.stdout, again.stdout
