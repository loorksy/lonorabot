"""Remove Stop entirely (owner amendment 1 to the Lonora Execution Mandate).

Lonora has no Stop control. The stored control, the cards of the ``resume_trading``
kind and the owner's ``emergency_stop`` attention items leave together with the code
that read them:

- The ``trading_control`` setting row (``enabled`` / ``emergency_stop``) is deleted.
  Nothing reads it any more; the execution door never consulted anything else for Stop.
  Production held ``enabled=true, emergency_stop=false``, so deleting it lifts nothing.
- Every owner-action row of kind ``resume_trading`` is deleted, whatever its status
  (14.3.9: rows of a kind are settled before the kind leaves the contract). No client
  renders that kind any more and no record references these rows; the card's only
  effect was the deleted setting.
- Every attention item with code ``emergency_stop`` is deleted: the code left the
  attention contract and its "still current" check read the deleted setting.

The downgrade restores nothing it cannot know. It writes the control back as running
(``enabled=true, emergency_stop=false``) so the older code, which treats a missing row as
"never started", does not stop new trading the owner never stopped. Deleted cards and
attention items are not recreated.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0150_remove_stop"
down_revision = "0135_workspace_given"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM ln_settings WHERE key = 'trading_control'"))
    connection.execute(sa.text("DELETE FROM ln_owner_actions WHERE kind = 'resume_trading'"))
    connection.execute(sa.text("DELETE FROM ln_attention WHERE code = 'emergency_stop'"))


def downgrade() -> None:
    connection = op.get_bind()
    settings = sa.table(
        "ln_settings",
        sa.column("key", sa.String),
        sa.column("payload", sa.JSON),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    exists = connection.execute(
        sa.text("SELECT 1 FROM ln_settings WHERE key = 'trading_control'")
    ).first()
    if exists is None:
        connection.execute(
            settings.insert().values(
                key="trading_control",
                payload={"enabled": True, "emergency_stop": False},
                updated_at=datetime.now(UTC),
            )
        )
