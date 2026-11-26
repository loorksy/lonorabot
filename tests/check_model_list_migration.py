"""Migration 0201 deletes the stored lists of the fixed providers (VISION 12.4).

On a disposable PostgreSQL one revision before it: store a ``catalog:<provider>`` row for
every provider, as discovery once did. The upgrade deletes every fixed provider's row and
keeps the owner endpoint's, whose models are the owner's. The downgrade restores nothing
and the upgrade runs again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime

from check_streaming import test_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
REVISION = "0201_fixed_model_list"
PROVIDERS = ("openai", "anthropic", "deepseek", "zai", "openrouter", "openai_compatible")


def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ALEMBIC, *arguments], capture_output=True, text=True, check=False)


async def catalogs(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text("SELECT key FROM ln_settings WHERE key LIKE 'catalog:%'")
            )
            return {row[0] for row in rows}
    finally:
        await engine.dispose()


async def main() -> None:
    url = test_settings().database_url
    assert alembic("upgrade", "head").returncode == 0
    downgraded = alembic("downgrade", REVISION + "-1")
    assert downgraded.returncode == 0, downgraded.stderr[-2000:]
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            for provider in PROVIDERS:
                model = {"id": "m", "provider": provider, "name": "M", "source": "discovered"}
                await connection.execute(
                    text(
                        "INSERT INTO ln_settings (key, payload, updated_at) VALUES"
                        " (:key, :payload, :now) ON CONFLICT (key) DO UPDATE"
                        " SET payload = excluded.payload"
                    ),
                    {
                        "key": "catalog:" + provider,
                        "payload": json.dumps({"models": [model]}),
                        "now": datetime.now(UTC),
                    },
                )
    finally:
        await engine.dispose()
    upgraded = alembic("upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr[-2000:]
    assert await catalogs(url) == {"catalog:openai_compatible"}, await catalogs(url)
    print("PASS the upgrade deletes the fixed providers' stored lists and keeps the endpoint's")
    downgraded = alembic("downgrade", REVISION + "-1")
    assert downgraded.returncode == 0, downgraded.stderr[-2000:]
    assert await catalogs(url) == {"catalog:openai_compatible"}
    assert alembic("upgrade", "head").returncode == 0
    print("PASS the downgrade restores nothing and the upgrade runs again")


if __name__ == "__main__":
    asyncio.run(main())
