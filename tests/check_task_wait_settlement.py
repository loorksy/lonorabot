"""Run the real Task wait ledger checks against an explicit disposable PostgreSQL DB."""

import os

import pytest
from lonora_api.env import get_settings
from sqlalchemy.engine import make_url


def main() -> None:
    url = get_settings().database_url
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql") or not (parsed.database or "").endswith(
        "_test"
    ):
        raise RuntimeError("Task wait checks require a disposable *_test PostgreSQL database")
    os.environ["LONORA_TASK_TEST_DATABASE_URL"] = url
    raise SystemExit(pytest.main(["tests/test_task_wait_settlement.py", "-q"]))


if __name__ == "__main__":
    main()
