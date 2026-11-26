"""The owner's reply language is a BCP-47 tag (es, zh-Hant, ...), not only ar or en.

The column widens from 8 to 35 characters and its check bounds the length; the tag's form
is validated where it is written (``owner_profile.ReplyLanguage``). Stored values (ar, en,
NULL) are already valid. The downgrade clears any other tag, then restores the old check.
"""

import sqlalchemy as sa
from alembic import op

revision = "0201_reply_language_tag"
down_revision = "0129_grant_cards_gone"
branch_labels = None
depends_on = None

TABLE, CHECK = "ln_owner_profile", "ln_owner_profile_reply_language"


def upgrade() -> None:
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.alter_column(TABLE, "reply_language", type_=sa.String(35), existing_type=sa.String(8))
    op.create_check_constraint(
        CHECK, TABLE, "reply_language IS NULL OR length(reply_language) BETWEEN 2 AND 35"
    )


def downgrade() -> None:
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.execute(
        "UPDATE ln_owner_profile SET reply_language = NULL WHERE reply_language NOT IN ('ar', 'en')"
    )
    op.alter_column(TABLE, "reply_language", type_=sa.String(8), existing_type=sa.String(35))
    op.create_check_constraint(
        CHECK, TABLE, "reply_language IS NULL OR reply_language IN ('ar','en')"
    )
