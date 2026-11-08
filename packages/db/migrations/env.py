import asyncio
from collections.abc import Mapping
from typing import Literal

from alembic import context
from lonora_api.env import get_settings
from lonora_db.schema import Base
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine


def include_name(
    name: str | None,
    kind: str,
    parent_names: Mapping[
        Literal["schema_name", "table_name", "schema_qualified_table_name"], str | None
    ],
) -> bool:
    return kind != "table" or bool(name and name.startswith("ln_"))


VERSION_TABLE = "lonora_v2_alembic"
# Revision ids are their file stems, and some are longer than Alembic's default
# VARCHAR(32) version column. Create the table wider, or widen it in place (a
# metadata-only change in PostgreSQL), before any revision is recorded.
VERSION_TABLE_DDL = (
    f"CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (version_num VARCHAR(128) NOT NULL, "
    f"CONSTRAINT {VERSION_TABLE}_pkc PRIMARY KEY (version_num))",
    f"ALTER TABLE {VERSION_TABLE} ALTER COLUMN version_num TYPE VARCHAR(128)",
)


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        version_table=VERSION_TABLE,
        include_name=include_name,
    )
    with context.begin_transaction():
        if connection.dialect.name == "postgresql":
            for statement in VERSION_TABLE_DDL:
                connection.execute(text(statement))
        context.run_migrations()


async def online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
