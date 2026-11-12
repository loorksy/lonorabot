"""Secrets by scope: per-agent secrets become the owner's workspace secrets.

A stored secret has one of four scopes: ``broker`` (broker passwords and the MetaApi
token), ``provider`` (model API keys), ``integration`` (feed, search, calendar and MCP
tokens) and ``workspace`` (the owner's secrets that agents use by name in the workspace,
VISION.md 7.2.4). Each ``agent:<id>`` secret moves to ``workspace`` under an environment
variable name: upper case, other characters become ``_``, a name not starting with a
letter gains ``S_``, at most 64 characters, and a name already taken gains ``_2``,
``_3``... The ciphertext is unchanged. Any other scope stops the upgrade with its name:
nothing ever wrote one, so none is guessed. The downgrade keeps the moved secrets in the
workspace scope (which agent saved one is not kept) and drops the scope check.
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "0070_secret_scopes"
down_revision = "0050_genui_state_and_origin"
branch_labels = None
depends_on = None

SCOPES = "scope IN ('broker','provider','integration','workspace')"


def workspace_name(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Z0-9_]", "_", name.upper())
    if not re.match(r"[A-Z]", base):
        base = "S_" + base
    base = base[:64]
    candidate, number = base, 1
    while candidate in taken:
        number += 1
        suffix = "_" + str(number)
        candidate = base[: 64 - len(suffix)] + suffix
    taken.add(candidate)
    return candidate


def upgrade() -> None:
    bind = op.get_bind()
    taken = set(
        bind.execute(sa.text("SELECT name FROM ln_secrets WHERE scope = 'workspace'")).scalars()
    )
    moved = bind.execute(
        sa.text(
            "SELECT id, name FROM ln_secrets WHERE scope LIKE 'agent:%' ORDER BY updated_at, id"
        )
    ).all()
    for secret_id, name in moved:
        bind.execute(
            sa.text("UPDATE ln_secrets SET scope = 'workspace', name = :name WHERE id = :id"),
            {"name": workspace_name(name, taken), "id": secret_id},
        )
    unknown = (
        bind.execute(
            sa.text(
                "SELECT DISTINCT scope FROM ln_secrets WHERE NOT (" + SCOPES + ") ORDER BY scope"
            )
        )
        .scalars()
        .all()
    )
    if unknown:
        # Nothing writes another scope; a row that has one is not guessed into a scope.
        raise RuntimeError("ln_secrets holds unknown scopes: " + ", ".join(unknown))
    op.create_check_constraint("ln_secret_scope", "ln_secrets", SCOPES)


def downgrade() -> None:
    op.drop_constraint("ln_secret_scope", "ln_secrets", type_="check")
