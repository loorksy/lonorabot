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
    "check_event_query_plans.py",
    "check_input_requests.py",
    "check_personal_agent.py",
    "check_skill_installation.py",
    "check_skills_versioning.py",
    "check_skill_authority_continuity.py",
    "check_skill_version_revocation.py",
    "check_owner_skill_catalog.py",
    "check_progressive_skills.py",
    "check_skill_repository.py",
    "check_skill_packages.py",
    "check_managed_skill_updates.py",
    "check_workspace_skill_creation.py",
    "check_workspace_artifacts.py",
    "check_workspace_migrations.py",
    "check_durable_records.py",
    "check_knowledge_retrieval.py",
    "check_conversation_recall.py",
    "check_tool_result_storage.py",
    "check_image_observations.py",
    "check_chart_snapshot_provenance.py",
    "check_chart_command_receipts.py",
    "check_chart_creation_receipts.py",
    "check_collaboration_sessions.py",
    "check_metaapi_discovery.py",
    "check_mcp_directory.py",
    "check_position_sizing.py",
    "check_market_health.py",
    "check_dynamic_watches.py",
    "check_market_structure.py",
    "check_market_analysis.py",
    "check_execution_quality.py",
    "check_decision_readiness.py",
    "check_llm_harness.py",
    "check_continuous_task_runtime.py",
    "check_task_wait_settlement.py",
    "check_task_continuation.py",
    "check_account_authority.py",
    "check_full_account_management.py",
    "check_management_task.py",
    "check_unified_permissions.py",
    "check_trading_mode.py",
    "check_trade_approvals.py",
    "check_account_recovery.py",
    "check_execution_recovery.py",
    "check_send_boundary.py",
    "check_owner_trades.py",
    "check_decision_replay.py",
    "check_review_findings.py",
    "check_delegated_scope.py",
    "check_watch_source_time.py",
    "check_opportunity_runtime.py",
    "check_shadow_removal_migration.py",
    "check_goal_removal_migration.py",
    "check_restriction_removal_migration.py",
    "check_money_limits_migration.py",
    "check_notice_card_migration.py",
    "check_flat_creation_migration.py",
    "check_pause_source_migration.py",
    "check_authority_migration.py",
    "check_task_recovery.py",
    "check_attention.py",
    "check_relationships.py",
    "check_device_authority.py",
    "check_activation_review.py",
    "check_conversational_setup.py",
    "check_agent_environment.py",
    "check_task_environment_wait.py",
    "check_voice_task_continuity.py",
    "check_voice_handoff_recovery.py",
    "check_incoming_calls.py",
    "check_runtime_collaboration.py",
    "check_memory_provenance.py",
    "check_owner_profile.py",
    "check_grant_coverage.py",
    "check_lossless_downgrades.py",
    "check_agent_model_choice.py",
    "check_agent_model_migration.py",
    "check_model_card_migration.py",
    "check_model_list_migration.py",
    "check_trust_migration.py",
    "check_simple_lonora.py",
    "check_gold_journey.py",
    "check_close_wake.py",
    "check_durable_runtime.py",
    "check_team.py",
    "check_group_replies.py",
    "check_broker_discovery.py",
    "check_market_runtime.py",
    "check_chart_tools.py",
    "check_chart_history.py",
    "check_generated_artifacts.py",
    "check_trading.py",
    "check_attention_items.py",
    "check_metaapi_adapter.py",
    "check_broker_history.py",
    "check_broker_recovery.py",
    "check_bound_market.py",
    "check_agent_binding.py",
    "check_flexible_agents.py",
    "check_broker_orders.py",
    "check_pending_orders.py",
    "check_chart_streaming.py",
    "check_agent_market.py",
    "check_agent_create.py",
    "check_supervision.py",
    "check_trusted_sources.py",
    "check_clients.py",
    "check_streaming.py",
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
    # 6.10: an attachment on the owner's message is not the owner's word.
    commands.append([sys.executable, "-m", "pytest", "tests/test_attachment_provenance.py", "-q"])
    # UI phase 5: delivery rules, dry-run tests, owner identity and usage, and the
    # composer's / commands; the owner's app opens and the learned brief time (PostgreSQL
    # cases).
    for name in (
        "test_agent_delivery_rules.py",
        "test_connection_tests.py",
        "test_model_providers.py",
        "test_model_provider_card.py",
        "test_owner_identity.py",
        "test_owner_profile.py",
        "test_usage_dashboard.py",
        "test_slash_commands.py",
        "test_usage_tool.py",
        "test_app_opens.py",
    ):
        commands.append([sys.executable, "-m", "pytest", "tests/" + name, "-q"])
    # Lonora's lead powers, and its delete of a team agent with the ticket transfer (3.1.2).
    for name in ("test_lead_powers.py", "test_delete_transfer.py"):
        commands.append([sys.executable, "-m", "pytest", "tests/" + name, "-q"])
    # The trading mode's ports of the grant and ladder checks (14.1.3).
    for name in ("test_mandate_card.py", "test_trading_mode_tools.py"):
        commands.append([sys.executable, "-m", "pytest", "tests/" + name, "-q"])
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
