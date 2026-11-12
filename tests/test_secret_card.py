"""The Secret card (VISION.md 7.2.1-7.2.4, 10.3).

The agent chooses the card's label and fields; the server sets the destination. The
owner's values go straight to the encrypted store in the transaction that settles the
card; the agent learns only which keys were saved, and no value reaches the card, an
event, a message or a run.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from lonora_db.schema import EventRow, MessageRow, OwnerActionRow, RunRow, SecretRow
from lonora_tools.loader import load_tools
from pydantic import ValidationError
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def test_the_agent_chooses_fields_and_the_server_the_destination() -> None:
    card = OwnerActionProposal.model_validate(
        {
            "kind": "secret",
            "label": "Binance",
            "secret_fields": [
                {"key": "BINANCE_API_KEY", "label": "API key"},
                {"key": "BINANCE_USER", "label": "User", "secret": False},
            ],
        }
    )
    assert card.secret_fields and card.secret_fields[1].secret is False
    for bad in (
        {"label": "x"},
        {"secret_fields": [{"key": "K", "label": "k"}]},
        {"label": "x", "secret_fields": [{"key": "lower", "label": "k"}]},
        {"label": "x", "secret_fields": [{"key": "K", "label": "a"}, {"key": "K", "label": "b"}]},
        # The destination is never the agent's choice; nor are other kinds' fields.
        {"label": "x", "secret_fields": [{"key": "K", "label": "k"}], "target": "broker"},
        {"label": "x", "secret_fields": [{"key": "K", "label": "k"}], "account_id": "a"},
    ):
        with pytest.raises(ValidationError):
            OwnerActionProposal.model_validate({"kind": "secret", **bad})
    with pytest.raises(ValidationError):
        OwnerActionProposal.model_validate(
            {"kind": "trust_source", "source_kind": "github_owner", "identifier": "x", "label": "y"}
        )


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The Secret card uses the PostgreSQL test database.")


async def call(context: Any, tool: str, /, **arguments: Any) -> dict[str, Any]:
    return await load_tools().execute(
        ToolCall(id="call-" + uuid4().hex, name=tool, arguments=arguments), context
    )


async def workspace(fixture: Any) -> dict[str, str]:
    return await fixture.runtime.services(fixture.owner).secrets.workspace_values()


@pytest.mark.asyncio
async def test_the_owner_saves_values_the_agent_never_sees() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    key, other = ("EXCHANGE_" + uuid4().hex[:6].upper() for _ in range(2))
    value, second = ("v-" + uuid4().hex for _ in range(2))
    try:
        agent = await fixture.agent("Keys")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        fields = [{"key": key, "label": "مفتاح API"}, {"key": other, "label": "Secret"}]
        proposed = await call(
            context, "owner_action_propose", kind="secret", label="بورصة", secret_fields=fields
        )
        card_id = proposed["owner_action"]["id"]
        cards = await fixture.request("GET", "/owner-actions?thread_id=" + context.thread_id)
        card: dict[str, Any] = next(item for item in cards if item["id"] == card_id)  # type: ignore[union-attr]
        assert card["kind"] == "secret" and card["status"] == "pending"
        assert card["facts"]["secret"] == {
            "label": "بورصة",
            "fields": [{**field, "secret": True} for field in fields],
            "destination": "workspace",
            "agent_name": agent["name"],
        }

        # A plain confirmation carries no values; wrong keys save nothing.
        confirm = await fixture.client.post(
            f"/api/owner-actions/{card_id}/decision", json={"decision": "confirm"}
        )
        assert confirm.status_code == 422
        assert confirm.json()["code"] == "owner_action_secret_values_required"
        for values in ({key: value}, {key: value, other: value, "EXTRA": "x"}):
            wrong = await fixture.client.post(
                f"/api/owner-actions/{card_id}/secret", json={"values": values}
            )
            assert wrong.status_code == 422, values
        async with fixture.runtime.db.sessions() as session:
            assert await session.scalar(select(SecretRow).where(SecretRow.name == key)) is None

        saved = await fixture.client.post(
            f"/api/owner-actions/{card_id}/secret", json={"values": {key: value, other: second}}
        )
        assert saved.status_code == 200
        assert saved.json()["status"] == "confirmed"
        assert saved.json()["result"] == {"saved": [key, other], "destination": "workspace"}
        assert (await workspace(fixture)).items() >= {key: value, other: second}.items()

        # A second submit shows the card as it is and writes nothing.
        again = await fixture.client.post(
            f"/api/owner-actions/{card_id}/secret", json={"values": {key: "x", other: "y"}}
        )
        assert again.status_code == 200 and again.json()["status"] == "confirmed"
        assert (await workspace(fixture))[key] == value

        async with fixture.runtime.db.sessions() as session:
            row = await session.get(OwnerActionRow, card_id)
            assert row is not None
            stored = json.dumps([row.payload, row.result])
            events = (
                await session.scalars(select(EventRow).where(EventRow.owner_id == fixture.owner))
            ).all()
            messages = (
                await session.scalars(
                    select(MessageRow).where(MessageRow.thread_id == context.thread_id)
                )
            ).all()
            runs = (
                await session.scalars(select(RunRow).where(RunRow.agent_id == agent["id"]))
            ).all()
        haystack = (
            stored
            + json.dumps(
                [[event.payload for event in events], [m.content for m in messages]], default=str
            )
            + json.dumps([[run.prompt, run.model_metadata] for run in runs], default=str)
        )
        assert value not in haystack and second not in haystack
        # The agent continues with the keys it asked for, never a value.
        follow = [run for run in runs if run.model_metadata.get("owner_action_id") == card_id]
        assert len(follow) == 1 and key in follow[0].prompt and other in follow[0].prompt

        # Not now saves nothing, and a later submit does not either.
        later = await call(
            context,
            "owner_action_propose",
            kind="secret",
            label="later",
            secret_fields=[{"key": key + "_X", "label": "k"}],
        )
        later_id = later["owner_action"]["id"]
        cancelled = await fixture.client.post(
            f"/api/owner-actions/{later_id}/decision", json={"decision": "cancel"}
        )
        assert cancelled.json()["status"] == "cancelled"
        after = await fixture.client.post(
            f"/api/owner-actions/{later_id}/secret", json={"values": {key + "_X": "v"}}
        )
        assert after.status_code == 200 and after.json()["status"] == "cancelled"
        assert key + "_X" not in await workspace(fixture)

        # Only a Secret card takes values.
        other_card = await call(
            context, "owner_action_propose", kind="connect_credential", target="news_feed"
        )
        refused = await fixture.client.post(
            f"/api/owner-actions/{other_card['owner_action']['id']}/secret",
            json={"values": {"K": "v"}},
        )
        assert refused.status_code == 409 and refused.json()["code"] == "owner_action_not_secret"
        with pytest.raises(LonoraError):
            await call(
                context,
                "owner_action_propose",
                kind="secret",
                label="x",
                secret_fields=[{"key": "bad-name", "label": "k"}],
            )
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                await session.scalars(
                    select(SecretRow).where(SecretRow.name.startswith("EXCHANGE_"))
                )
            ).all():
                await session.delete(row)
        await fixture.close()
