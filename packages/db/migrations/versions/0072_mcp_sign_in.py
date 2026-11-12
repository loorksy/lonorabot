"""A sign-in to an MCP server from the Secret card (VISION.md 13.1).

``ln_mcp_sign_ins`` holds a sign-in the owner started, until the authorization server
sends the owner's browser back: its state as a digest, where its tokens come from, and,
encrypted, its PKCE verifier, the server's address and any client secret. An MCP
connection signed in this way keeps an ``oauth`` record in its payload (the access token
is its ``secret_id``).

The downgrade refuses while a connection keeps an ``oauth`` record: the earlier release
cannot read it. Remove those connections first. It then drops the table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0072_mcp_sign_in"
down_revision = "0071_secret_card_kinds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_mcp_sign_ins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "card_id",
            sa.String(36),
            sa.ForeignKey("ln_owner_actions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("failure", sa.String(80)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ln_mcp_sign_ins_card_id", "ln_mcp_sign_ins", ["card_id"])


def downgrade() -> None:
    signed_in = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM ln_mcp_connections WHERE payload->'oauth' IS NOT NULL"
                " AND json_typeof(payload->'oauth') = 'object'"
            )
        )
        .scalar_one()
    )
    if signed_in:
        raise RuntimeError(
            f"{signed_in} MCP connection(s) were signed in with OAuth, which the earlier "
            "release cannot read: remove them first"
        )
    op.drop_index("ix_ln_mcp_sign_ins_card_id", "ln_mcp_sign_ins")
    op.drop_table("ln_mcp_sign_ins")
