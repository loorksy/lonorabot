"""Run integration fixtures in newly created disposable PostgreSQL databases.

Unlike chaining fixture scripts on a shared owner database, each process has an
independent authenticated owner and leaves no state for the next fixture.
"""

import asyncio
import os
import subprocess
import sys
from uuid import uuid4

from lonora_api.env import get_settings
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

CHECKS = (
    "check_model_context.py",
    "check_input_requests.py",
    "check_personal_agent.py",
    "check_skill_installation.py",
    "check_skills_versioning.py",
    "check_skill_authority_continuity.py",
    "check_skill_version_revocation.py",
    "check_owner_skill_catalog.py",
    "check_progressive_skills.py",
    "check_skill_repository.py",
    "check_knowledge_retrieval.py",
    "check_conversation_recall.py",
    "check_tool_result_storage.py",
    "check_image_observations.py",
    "check_chart_snapshot_provenance.py",
    "check_chart_command_receipts.py",
    "check_chart_creation_receipts.py",
    "check_collaboration_sessions.py",
    "check_metaapi_discovery.py",
    "check_market_health.py",
    "check_dynamic_watches.py",
    "check_execution_quality.py",
    "check_account_recovery.py",
    "check_decision_replay.py",
    "check_review_findings.py",
    "check_delegated_scope.py",
    "check_watch_source_time.py",
    "check_opportunity_runtime.py",
    "check_shadow_runtime.py",
    "check_shadow_goals.py",
    "check_task_recovery.py",
    "check_attention.py",
    "check_relationships.py",
    "check_device_authority.py",
    "check_activation_review.py",
    "check_conversational_setup.py",
    "check_agent_environment.py",
    "check_task_environment_wait.py",
    "check_voice_task_continuity.py",
    "check_runtime_collaboration.py",
    "check_memory_provenance.py",
    "check_goal_call_identity.py",
)


async def database(base: URL, name: str, *, create: bool) -> None:
    # Identifier is generated internally, never supplied by the model/user.
    assert name.startswith("lonora_foundation_") and name.endswith("_test") and name.isidentifier()
    engine = create_async_engine(base.set(database="postgres"))
    try:
        async with engine.connect() as connection:
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(
                text(("CREATE DATABASE " if create else "DROP DATABASE ") + name)
            )
    finally:
        await engine.dispose()


def main() -> None:
    if sys.argv[1:] != ["--isolated-databases"]:
        raise SystemExit("Pass --isolated-databases to create and remove disposable test databases")
    base = make_url(get_settings().database_url)
    commands = [[sys.executable, "tests/" + script] for script in CHECKS]
    commands.append([sys.executable, "-m", "pytest", "tests/test_task_runtime.py", "-q"])
    for command in commands:
        name = "lonora_foundation_" + uuid4().hex + "_test"
        asyncio.run(database(base, name, create=True))
        try:
            env = os.environ.copy()
            url = base.set(database=name).render_as_string(hide_password=False)
            env["LONORA_DATABASE_URL"] = url
            env["LONORA_TASK_TEST_DATABASE_URL"] = url
            subprocess.run(["bash", "scripts/migrate.sh"], env=env, check=True)
            print("RUN", command[-1], flush=True)
            subprocess.run(command, env=env, check=True)
        finally:
            asyncio.run(database(base, name, create=False))
    print("All isolated foundation integrations passed", flush=True)


if __name__ == "__main__":
    main()
