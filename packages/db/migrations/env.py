import asyncio
from collections.abc import Mapping
from typing import Literal

from alembic import context
from lonora_api.env import get_settings
from lonora_db.schema import Base
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


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        version_table="lonora_v2_alembic",
        include_name=include_name,
    )
    with context.begin_transaction():
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
        version_table="lonora_v2_alembic",
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
