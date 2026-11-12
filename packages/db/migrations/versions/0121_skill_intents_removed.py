"""Skill manifests no longer carry ``activation.intents`` (mandate section 13).

Intent selection never fired: the runtime passed no intents, so the setting was dead
configuration. ``SkillManifest`` validates with ``extra="forbid"``, so every stored copy of
a manifest loses the key before the field is removed from the contract (14.3.9):

- ``ln_skills.payload.manifest`` and each package version inside ``ln_skills.state``;
- ``ln_skill_versions.payload.manifest``;
- the pinned manifests in ``ln_runs.model_metadata.skill_snapshot``.

The downgrade has nothing to restore: the earlier contract reads a missing key as [].
"""

import json
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0121_skill_intents_removed"
down_revision = "0138_skill_package_files"
branch_labels = None
depends_on = None


def _loaded(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _mapping(value: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _strip_manifest(manifest: Any) -> bool:
    activation = _mapping((_mapping(manifest) or {}).get("activation"))
    if activation is not None and "intents" in activation:
        del activation["intents"]
        return True
    return False


def _strip_payload(payload: Any) -> bool:
    return _strip_manifest((_mapping(payload) or {}).get("manifest"))


def _rewrite(table: str, key: str, column: str, strip: Any) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(f"SELECT {key}, {column} FROM {table} WHERE {column}::text LIKE '%\"intents\"%'")
    ).all()
    for identity, raw in rows:
        value = _loaded(raw)
        if strip(value):
            connection.execute(
                sa.text(f"UPDATE {table} SET {column} = CAST(:value AS JSON) WHERE {key} = :key"),
                {"value": json.dumps(value), "key": identity},
            )


def _strip_state(state: Any) -> bool:
    package = _mapping((_mapping(state) or {}).get("package")) or {}
    versions: Any = package.get("versions")
    changed = False
    for entry in cast(list[Any], versions) if isinstance(versions, list) else []:
        if _strip_payload((_mapping(entry) or {}).get("payload")):
            changed = True
    return changed


def _strip_snapshot(metadata: Any) -> bool:
    snapshot = _mapping((_mapping(metadata) or {}).get("skill_snapshot")) or {}
    skills = _mapping(snapshot.get("skills")) or {}
    changed = False
    for entry in skills.values():
        if _strip_manifest((_mapping(entry) or {}).get("manifest")):
            changed = True
    return changed


def upgrade() -> None:
    _rewrite("ln_skills", "id", "payload", _strip_payload)
    _rewrite("ln_skills", "id", "state", _strip_state)
    _rewrite("ln_runs", "id", "model_metadata", _strip_snapshot)
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT skill_id, version, payload FROM ln_skill_versions "
            "WHERE payload::text LIKE '%\"intents\"%'"
        )
    ).all()
    for skill_id, version, raw in rows:
        payload = _loaded(raw)
        if _strip_payload(payload):
            connection.execute(
                sa.text(
                    "UPDATE ln_skill_versions SET payload = CAST(:value AS JSON) "
                    "WHERE skill_id = :skill AND version = :version"
                ),
                {"value": json.dumps(payload), "skill": skill_id, "version": version},
            )


def downgrade() -> None:
    pass
