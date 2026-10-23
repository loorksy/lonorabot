"""Only trusted deployment configuration may declare external tool effects."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from lonora_api.env import Settings
from lonora_api.runtime import ApiRuntime
from lonora_contracts.mcp import McpConnection, McpToolDeclaration
from lonora_contracts.runs import Lease
from lonora_db.schema import Base
from lonora_gateway.runtime import OwnerServices
from lonora_worker.runtime import create_gateway
from pydantic import SecretStr, ValidationError


def declaration() -> McpToolDeclaration:
    return McpToolDeclaration(
        owner_id="fixture-owner",
        connection_id="fixture-connection",
        endpoint_sha256="a" * 64,
        tool_name="inspect_fixture",
        input_schema_sha256="b" * 64,
    )


def configuration(**changes: object) -> Settings:
    return Settings.model_validate(
        {
            "database_url": "sqlite+aiosqlite:///:memory:",
            "encryption_key": SecretStr(Fernet.generate_key().decode()),
            "bootstrap_token": SecretStr("fixture-configuration-not-a-production-key"),
            **changes,
        }
    )


def test_operator_policy_defaults_closed_and_rejects_duplicate_or_write_declarations() -> None:
    assert configuration().mcp_declarations == ()
    reviewed = declaration()
    with pytest.raises(ValidationError):
        configuration(mcp_declarations=[reviewed, reviewed])
    with pytest.raises(ValidationError):
        McpToolDeclaration.model_validate({**reviewed.model_dump(), "effect": "financial"})
    with pytest.raises(ValidationError):
        McpToolDeclaration.model_validate({**reviewed.model_dump(), "credential_scope": "broker"})
    with pytest.raises(ValidationError):
        reviewed.effect = "read_only"
    with pytest.raises(ValidationError):
        McpConnection.model_validate({"name": "owner setting", "declarations": [reviewed]})


def test_environment_policy_is_typed_and_not_a_remote_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    reviewed = declaration()
    monkeypatch.setenv("LONORA_MCP_DECLARATIONS", json.dumps([reviewed.model_dump()]))
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        encryption_key=SecretStr(Fernet.generate_key().decode()),
        bootstrap_token=SecretStr("fixture-configuration-not-a-production-key"),
    )
    assert settings.mcp_declarations == (reviewed,)


@pytest.mark.asyncio
async def test_declaration_reaches_api_gateway_and_same_agent_child_context(tmp_path: Path) -> None:
    reviewed = declaration()
    settings = configuration(mcp_declarations=[reviewed], artifact_root=tmp_path)
    db, gateway = create_gateway(settings)
    api = ApiRuntime.create(settings)
    services = OwnerServices.create(
        db,
        "fixture-owner",
        settings.encryption_key.get_secret_value(),
        mcp_declarations=gateway.mcp_declarations,
    )
    try:
        for database in (db, api.db):
            async with database.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        assert gateway.mcp_declarations == (reviewed,)
        assert api.services("fixture-owner").mcp_declarations == (reviewed,)
        context = services.tool_context(
            "fixture-agent",
            "fixture-thread",
            Lease(run_id="fixture-run", owner="fixture-worker", fence=1),
            tmp_path,
        )
        assert context.mcp_declarations == (reviewed,)
        assert context.for_call("fixture-call").mcp_declarations == (reviewed,)
        assert replace(context, depth=1).mcp_declarations == (reviewed,)
        # Runtime policy carries exact owner identity; another owner cannot use it.
        assert api.services("other-owner").mcp_declarations[0].owner_id == "fixture-owner"
    finally:
        await services.close()
        await api.close()
        await db.close()
