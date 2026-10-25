"""Index delivery and bounded context reads without rewriting the event ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0031_event_delivery_indexes"
down_revision = "0030_full_account_management"
branch_labels = None
depends_on = None

INDEXES = (
    (
        "ln_events_owner_public_cursor",
        "owner_id, (CAST(payload ->> '_ln_public_cursor' AS INTEGER))",
        "",
    ),
    (
        "ln_events_unpublished_cursor",
        "cursor",
        " WHERE CAST(payload ->> '_ln_public_cursor' AS INTEGER) IS NULL",
    ),
    ("ln_events_run_cursor", "run_id, cursor", ""),
    ("ln_events_owner_agent_kind_cursor", "owner_id, agent_id, kind, cursor", ""),
)


def upgrade() -> None:
    # Concurrent DDL keeps normal event/message admission available. Interrupted
    # PostgreSQL builds can leave an INVALID index: IF NOT EXISTS alone would
    # silently retain it, so repair that exact migration-owned name on retry.
    for name, columns, predicate in INDEXES:
        with op.get_context().autocommit_block():
            if not op.get_context().as_sql:
                valid = (
                    op.get_bind()
                    .execute(
                        sa.text(
                            "SELECT i.indisvalid AND i.indisready "
                            "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                            "WHERE c.relname = :name "
                            "AND c.relnamespace = current_schema()::regnamespace"
                        ),
                        {"name": name},
                    )
                    .scalar()
                )
                if valid is False:
                    op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"'))
            op.execute(
                sa.text(
                    f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{name}" '
                    f"ON ln_events ({columns}){predicate}"
                )
            )


def downgrade() -> None:
    for name, _, _ in reversed(INDEXES):
        with op.get_context().autocommit_block():
            op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"'))
