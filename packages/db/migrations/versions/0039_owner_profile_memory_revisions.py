"""One owner profile every agent reads, and attributed, revertible memory revisions.

The data step merges each agent's legacy ``# USER.md`` section into the owner profile,
oldest change first, keeping each distinct line once under a provenance comment that
names its source agent. Agent rows keep their text; the runtime no longer reads
USER.md from them. The merge is keyed on the resulting content hash, so running it
again changes nothing. The downgrade first keeps every profile line the agent rows do
not already hold (the owner's edits since the upgrade) as a ``# USER.md`` section of the
Personal Agent's document, where the earlier runtime reads it and the re-upgrade merges
it from; then it drops the new tables (the revision history goes with them).
"""

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0039_owner_profile_memory_revisions"
down_revision = "0038_owner_actions"
branch_labels = None
depends_on = None

# The view headings the runtime recognizes (lonora_memory.profile), frozen here.
VIEW_HEADING = re.compile(r"(?m)^# (USER\.md|OPERATING\.md|(?:memory/)?MEMORY\.md)[ \t]*\n")


def user_section(content: str) -> str:
    """Every legacy ``# USER.md`` body of one agent document, in order."""
    parts = VIEW_HEADING.split(content)
    bodies = [
        parts[index + 1].strip()
        for index in range(1, len(parts), 2)
        if parts[index] == "USER.md" and parts[index + 1].strip()
    ]
    return "\n\n".join(bodies)


def provenance(name: str) -> str:
    safe = re.sub(r"\s+", " ", name.replace("--", "-").replace(">", "")).strip() or "an agent"
    return f"<!-- Merged from {safe[:80]} -->"


# The owner profile's limit (lonora_db.owner_profile.OWNER_PROFILE_CHAR_LIMIT), frozen here.
PROFILE_LIMIT = 8000
OVERFLOW_HEADING = "## Owner preferences kept here (the shared profile was full)"


def merge_profile(existing: str, sources: list[tuple[str, str]]) -> str:
    """Append each source's lines not already present (exact, trimmed), latest last."""
    seen = {line.strip() for line in existing.splitlines() if line.strip()}
    blocks = [existing.strip()] if existing.strip() else []
    for name, body in sources:
        kept: list[str] = []
        for line in body.splitlines():
            key = line.strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            kept.append(line.rstrip())
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
        if text:
            blocks.append(provenance(name) + "\n" + text)
    return "\n\n".join(blocks) + "\n" if blocks else ""


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def merge_owner(connection: Any, owner_id: str, now: datetime) -> bool:
    """Merge one owner's legacy sections; True when the profile changed."""
    rows = connection.execute(
        sa.text(
            "SELECT a.name, m.content FROM ln_memory m JOIN ln_agents a ON a.id = m.agent_id "
            "WHERE a.owner_id = :owner ORDER BY m.updated_at, a.created_at, a.id"
        ),
        {"owner": owner_id},
    ).all()
    sources = [(str(name), user_section(str(content))) for name, content in rows]
    sources = [(name, body) for name, body in sources if body]
    profile = connection.execute(
        sa.text("SELECT content, version FROM ln_owner_profile WHERE owner_id = :owner"),
        {"owner": owner_id},
    ).first()
    existing = str(profile[0]) if profile else ""
    merged = merge_profile(existing, sources)
    if len(merged) > PROFILE_LIMIT:
        merged = keep_overflow(connection, owner_id, existing, sources, now)
    if content_hash(merged) == content_hash(existing):
        return False
    version = (int(profile[1]) + 1) if profile else 1
    if profile:
        connection.execute(
            sa.text(
                "UPDATE ln_owner_profile SET content = :content, version = :version, "
                "updated_at = :now WHERE owner_id = :owner"
            ),
            {"content": merged, "version": version, "now": now, "owner": owner_id},
        )
    else:
        connection.execute(
            sa.text(
                "INSERT INTO ln_owner_profile (owner_id, content, version, updated_at) "
                "VALUES (:owner, :content, :version, :now)"
            ),
            {"content": merged, "version": version, "now": now, "owner": owner_id},
        )
    connection.execute(
        sa.text(
            "INSERT INTO ln_memory_revisions (id, owner_id, document, agent_id, version, "
            "previous_content, content, author, change, created_at) VALUES (:id, :owner, "
            "'owner_profile', NULL, :version, :previous, :content, 'system', 'merge', :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "owner": owner_id,
            "version": version,
            "previous": existing,
            "content": merged,
            "now": now,
        },
    )
    return True


def keep_overflow(
    connection: Any, owner_id: str, existing: str, sources: list[tuple[str, str]], now: datetime
) -> str:
    """A merge past the profile's limit: whole agent blocks join the shared profile, oldest
    first, while they fit; each block that does not fit is routed, not dropped, into that
    agent's own operating notes (``# OPERATING.md``), which only it reads, under a heading
    that says why. Rules are never deleted (correction 16)."""
    kept: list[tuple[str, str]] = []
    for name, body in sources:
        if len(merge_profile(existing, [*kept, (name, body)])) <= PROFILE_LIMIT:
            kept.append((name, body))
            continue
        rows = connection.execute(
            sa.text(
                "SELECT m.agent_id, m.content FROM ln_memory m JOIN ln_agents a "
                "ON a.id = m.agent_id WHERE a.owner_id = :owner AND a.name = :name"
            ),
            {"owner": owner_id, "name": name},
        ).all()
        for agent_id, content in rows:
            text = str(content)
            if user_section(text) != body or OVERFLOW_HEADING in text:
                continue
            note = f"# OPERATING.md\n{OVERFLOW_HEADING}\n{body.strip()}\n"
            connection.execute(
                sa.text(
                    "UPDATE ln_memory SET content = :content, version = version + 1, "
                    "updated_at = :now WHERE agent_id = :agent"
                ),
                {"agent": agent_id, "content": text.rstrip() + "\n\n" + note, "now": now},
            )
    return merge_profile(existing, kept)


def merge_legacy_user_sections(connection: Any) -> int:
    now = datetime.now(UTC)
    owners = connection.execute(sa.text("SELECT id FROM ln_owners ORDER BY id")).scalars().all()
    return sum(merge_owner(connection, str(owner), now) for owner in owners)


def upgrade() -> None:
    op.create_table(
        "ln_owner_profile",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reply_language", sa.String(8)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reply_language IS NULL OR reply_language IN ('ar','en')",
            name="ln_owner_profile_reply_language",
        ),
    )
    op.create_table(
        "ln_memory_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document", sa.String(24), nullable=False),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ln_agents.id", ondelete="CASCADE")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("previous_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("author", sa.String(8), nullable=False),
        sa.Column(
            "author_agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_message_id",
            sa.String(36),
            sa.ForeignKey("ln_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("source_run_id", sa.String(36)),
        sa.Column("change", sa.String(16), nullable=False),
        sa.Column("reverted_revision_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "document IN ('owner_profile','owner_preferences','agent_memory')",
            name="ln_memory_revision_document",
        ),
        sa.CheckConstraint(
            "(document = 'agent_memory') = (agent_id IS NOT NULL)",
            name="ln_memory_revision_agent",
        ),
        sa.CheckConstraint(
            "author IN ('owner','agent','system')", name="ln_memory_revision_author"
        ),
    )
    op.create_index(
        "ix_ln_memory_revisions_document",
        "ln_memory_revisions",
        ["owner_id", "document", "agent_id", "created_at"],
    )
    merge_legacy_user_sections(op.get_bind())


def restore_legacy_profiles(connection: Any) -> int:
    """Keep every profile line the agent rows do not already hold: the owner's own edits
    and agents' writes since the upgrade exist only in the profile. They are appended as
    a ``# USER.md`` section of the Personal Agent's document (else the owner's oldest
    agent), where the earlier runtime reads owner preferences and the re-upgrade merges
    them from. A profile the agent rows already rebuild changes no row. An owner with
    lines to keep and no agent to hold them stops the downgrade."""
    now = datetime.now(UTC)
    restored = 0
    for owner_id, content in connection.execute(
        sa.text("SELECT owner_id, content FROM ln_owner_profile WHERE content <> ''")
    ).all():
        rows = connection.execute(
            sa.text(
                "SELECT m.content FROM ln_memory m JOIN ln_agents a ON a.id = m.agent_id "
                "WHERE a.owner_id = :owner"
            ),
            {"owner": owner_id},
        ).scalars()
        known = {
            line.strip()
            for document in rows
            for line in user_section(str(document)).splitlines()
            if line.strip()
        }
        missing = [
            line.rstrip()
            for line in str(content).splitlines()
            if line.strip() and not line.startswith("<!--") and line.strip() not in known
        ]
        if not missing:
            continue
        holder = connection.execute(
            sa.text(
                "SELECT id FROM ln_agents WHERE owner_id = :owner "
                "ORDER BY (role = 'personal') DESC, created_at, id LIMIT 1"
            ),
            {"owner": owner_id},
        ).scalar()
        if holder is None:
            raise RuntimeError("Cannot downgrade: an owner profile has no agent to keep it")
        section = "# USER.md\n" + "\n".join(missing) + "\n"
        row = connection.execute(
            sa.text("SELECT content FROM ln_memory WHERE agent_id = :agent"),
            {"agent": holder},
        ).first()
        if row is None:
            connection.execute(
                sa.text(
                    "INSERT INTO ln_memory (agent_id, content, version, updated_at) "
                    "VALUES (:agent, :content, 1, :now)"
                ),
                {"agent": holder, "content": section, "now": now},
            )
        else:
            current = str(row[0]).rstrip()
            connection.execute(
                sa.text(
                    "UPDATE ln_memory SET content = :content, version = version + 1, "
                    "updated_at = :now WHERE agent_id = :agent"
                ),
                {
                    "agent": holder,
                    "content": (current + "\n\n" if current else "") + section,
                    "now": now,
                },
            )
        restored += 1
    return restored


def downgrade() -> None:
    restore_legacy_profiles(op.get_bind())
    op.drop_index("ix_ln_memory_revisions_document", table_name="ln_memory_revisions")
    op.drop_table("ln_memory_revisions")
    op.drop_table("ln_owner_profile")
