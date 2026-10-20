"""Actual signed WebAuthn assertions bind owner/session/goal/permissions."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_auth.devices import begin_activation, finish_activation
from lonora_auth.sessions import read_session
from lonora_contracts.domain import utcnow
from lonora_contracts.super_bot import DeviceProof, SuperBotProposal
from lonora_core.user_error import LonoraError
from lonora_db.attention import mandatory_current
from lonora_db.schema import AttentionRow, DeviceChallengeRow, SuperBotRequestRow
from lonora_db.super_bot import propose, require_goal_authority
from lonora_db.trading_goals import owned_goal
from lonora_gateway.attention import attention_tick
from lonora_tools.loader import load_tools
from sqlalchemy import select


async def main():
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "device-authority", "enabled": True},
            )
        )["id"]
        agent = await f.agent("Device authority")
        thread = await f.conversation(agent)
        body = {
            "agent_id": agent["id"],
            "thread_id": thread["id"],
            "title": "Bound signed goal",
            "objective": "Observe and manage only this reviewed plan",
            "account_id": account,
            "symbol": "EURUSDm",
            "maximum_volume": "0.1",
            "max_trade_actions": 1,
            "steps": [{"id": "read", "title": "Read source", "kind": "analysis"}],
        }
        goal = await f.request("POST", "/trading/goals", body)
        rejected = await f.client.post(
            f"/api/trading/goals/{goal['id']}/control",
            json={"version": goal["version"], "action": "resume", "autonomous": True},
        )
        assert (
            rejected.status_code == 403
            and rejected.json()["code"] == "device_authorization_required"
        )
        device = await Device.enroll(f)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()
        proposal_call = ToolCall(
            id="signed-proposal-fixture",
            name="super_bot_propose",
            arguments={"goal_id": goal["id"], "mode": "autonomous"},
        )
        proposal = await registry.execute(proposal_call, context)
        from lonora_db.activation_review import dispatch_activation_reviews

        assert await dispatch_activation_reviews(f.runtime.db) == 0
        assert proposal["status"] == "pending"
        projected = cast(
            list[dict[str, Any]], await f.request("GET", f"/agents/{agent['id']}/super-bot")
        )
        anchored = next(item for item in projected if item["id"] == proposal["id"])
        assert anchored["created_at"] == proposal["created_at"]
        assert isinstance(anchored["timeline_seq"], int) and anchored["timeline_seq"] >= 1
        live = await f.request("GET", f"/agents/{agent['id']}/state")
        assert live["state"] == "action_required" and live["pending_authorization_count"] == 1
        assert (
            live["super_bot"][0]["authorization_status"] == "pending"
            and live["super_bot"][0]["autonomous"] is False
        )
        assert (await f.request("GET", "/trading/goals/" + goal["id"]))["state"][
            "autonomous"
        ] is False

        duplicate = await f.request(
            "POST",
            f"/agents/{agent['id']}/super-bot/proposals",
            {"goal_id": goal["id"], "mode": "autonomous"},
        )
        assert duplicate["id"] == proposal["id"] and proposal["status"] == "pending"
        await attention_tick(f.runtime.db, f.runtime.services(f.owner).brokers, f.owner)
        async with f.runtime.db.sessions() as session:
            notice = await session.scalar(
                select(AttentionRow).where(AttentionRow.code == "super_bot_authorization")
            )
            assert (
                notice
                and notice.importance == "action_required"
                and await mandatory_current(session, notice)
            )
            notice_id = notice.id
        challenge = await f.request("POST", f"/super-bot/{proposal['id']}/challenge", {})
        proof = device.assertion(challenge, f.settings.allowed_origin)
        result = await f.request("POST", "/super-bot/verify", proof)
        assert result["status"] == "activated"
        projected = cast(
            list[dict[str, Any]], await f.request("GET", f"/agents/{agent['id']}/super-bot")
        )
        resolved_anchor = next(item for item in projected if item["id"] == proposal["id"])
        assert resolved_anchor["timeline_seq"] == anchored["timeline_seq"]
        assert resolved_anchor["created_at"] == anchored["created_at"]
        live = await f.request("GET", f"/agents/{agent['id']}/state")
        assert (
            live["pending_authorization_count"] == 0 and live["super_bot"][0]["autonomous"] is True
        )
        replayed_tool = await registry.execute(proposal_call, context)
        assert replayed_tool["id"] == proposal["id"] and replayed_tool["status"] == "activated"

        async with f.runtime.db.sessions() as session:
            notice = await session.get(AttentionRow, notice_id)
            assert notice and not await mandatory_current(session, notice)

        assert (await f.request("POST", "/super-bot/verify", proof))["id"] == result["id"]
        async with f.runtime.db.sessions() as session:
            saved = await owned_goal(session, f.owner, goal["id"])
            assert saved.state["autonomous"] is True
            await require_goal_authority(session, saved)
        assert (await f.request("GET", "/trading/controls"))["enabled"] is False
        print(
            "PASS password-confirmed credential enrollment, signed UV activation, exact frozen scope, pending dedup and lost-response replay; global trading stays OFF"
        )

        goal = await f.request("GET", "/trading/goals/" + goal["id"])
        expanded = await f.client.post(
            f"/api/trading/goals/{goal['id']}/control",
            json={"version": goal["version"], "action": "resume", "maximum_volume": "0.2"},
        )
        assert expanded.status_code == 403
        await f.request(
            "POST", "/super-bot/control", {"request_id": proposal["id"], "action": "pause"}
        )
        assert (await f.request("POST", "/super-bot/verify", proof))["status"] == "paused"
        assert (await f.request("GET", "/trading/goals/" + goal["id"]))["state"][
            "autonomous"
        ] is False
        print(
            "PASS authority expansion is blocked; pause requires no new device proof and replay cannot reactivate paused authority"
        )

        # Use the same real verification function for adversarial cases without
        # consuming the unrelated per-process HTTP password rate-limit budget.
        async with f.runtime.db.sessions() as session:
            identity = await read_session(session, f.client.cookies.get("lonora_session"))
        new = await f.request(
            "POST",
            f"/agents/{agent['id']}/super-bot/proposals",
            {"goal_id": goal["id"], "mode": "autonomous"},
        )

        async def denied(payload: dict[str, Any], code: str):
            try:
                async with f.runtime.db.sessions() as session, session.begin():
                    await finish_activation(
                        session,
                        identity,
                        DeviceProof.model_validate(payload),
                        f.settings.allowed_origin,
                    )
            except LonoraError as error:
                assert error.code == code, error.code
            else:
                raise AssertionError("invalid authority accepted")

        missing_uv = await f.request("POST", f"/super-bot/{new['id']}/challenge", {})
        await denied(
            device.assertion(missing_uv, f.settings.allowed_origin, verified=False),
            "device_proof_invalid",
        )
        wrong_origin = device.assertion(missing_uv, "https://different.example")
        await denied(wrong_origin, "device_proof_invalid")
        forged = device.assertion(missing_uv, f.settings.allowed_origin)
        forged["credential"]["response"]["signature"] = "AAAA"
        await denied(forged, "device_proof_invalid")
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(DeviceChallengeRow, missing_uv["challenge_id"])
            assert row
            row.expires_at = utcnow() - timedelta(seconds=1)
        await denied(
            device.assertion(missing_uv, f.settings.allowed_origin),
            "device_challenge_expired_or_used",
        )
        fresh = await f.request("POST", f"/super-bot/{new['id']}/challenge", {})
        async with f.runtime.db.sessions() as session, session.begin():
            request = await session.get(SuperBotRequestRow, new["id"])
            assert request
            request.envelope = {**request.envelope, "max_trade_actions": 40}
        await denied(
            device.assertion(fresh, f.settings.allowed_origin),
            "super_bot_request_expired_or_changed",
        )
        print(
            "PASS missing signed UV, wrong origin/RP, forged signature, expired challenge and changed permission envelope fail closed"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            corrupted = await session.get(SuperBotRequestRow, new["id"])
            assert corrupted
            corrupted.status = "rejected"
            await session.flush()
            row = await propose(
                session,
                f.owner,
                agent["id"],
                SuperBotProposal(goal_id=goal["id"], mode="autonomous"),
            )
            challenge = await begin_activation(session, identity, row.id, f.settings.allowed_origin)
        valid = device.assertion(challenge, f.settings.allowed_origin)
        try:
            async with f.runtime.db.sessions() as session, session.begin():
                await finish_activation(
                    session,
                    replace(identity, token_hash="different-session"),
                    DeviceProof.model_validate(valid),
                    f.settings.allowed_origin,
                )
        except LonoraError as error:
            assert error.code == "device_challenge_not_found"
        else:
            raise AssertionError("cross-session device proof accepted")
        async with f.runtime.db.sessions() as session, session.begin():
            activated = await finish_activation(
                session, identity, DeviceProof.model_validate(valid), f.settings.allowed_origin
            )
            activated_id = activated.id
        devices = cast(list[dict[str, Any]], await f.request("GET", "/auth/devices"))
        await f.request("DELETE", "/auth/devices/" + devices[0]["id"])
        async with f.runtime.db.sessions() as session:
            saved = await owned_goal(session, f.owner, goal["id"])
            assert saved.state["autonomous"] is False
            try:
                await require_goal_authority(session, saved)
            except LonoraError as error:
                assert error.code == "device_authorization_required"
            else:
                raise AssertionError("revoked credential retained authority")
        async with f.runtime.db.sessions() as session, session.begin():
            replay = await finish_activation(
                session, identity, DeviceProof.model_validate(valid), f.settings.allowed_origin
            )
            assert replay.id == activated_id and replay.status == "disabled"
        print(
            "PASS cross-session proof isolation, device revocation and replay after revocation cannot restore authority"
        )

    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
