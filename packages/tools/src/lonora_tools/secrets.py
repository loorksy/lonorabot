"""The owner's workspace secrets from chat (VISION.md P5, 7.2.4).

The owner asks in chat which secrets are saved, and removes one in his own words. A
value never comes back: only names, when each was saved, and the connections that name
it. Deleting goes through the one deletion of a stored secret (``delete_secret``), the
same as ``DELETE /secrets/{secret_id}``, which stays the only route that deletes one
(14.3.11). Only the owner's typed words this Run answers can ask for it, and they must
name the secret (as a model switch must name the model); a secret a connection uses is
not deleted.
"""

import re
from typing import Any

from lonora_contracts.agent_secrets import WORKSPACE_SECRET_NAME
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, MessageRow, RunRow, SecretRow, SteeringRow
from lonora_db.secrets import WORKSPACE, delete_secret, workspace_secrets
from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool
from .context import ToolContext
from .restrictions import owner_message_id


class SecretsListInput(Contract):
    pass


class SecretDeleteInput(Contract):
    name: str = Field(pattern=WORKSPACE_SECRET_NAME)


async def listing(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    SecretsListInput.model_validate(args)
    async with context.db.sessions() as session:
        secrets = await workspace_secrets(session, context.owner_id)
    return {
        "secrets": secrets,
        "values_returned": False,
        "guidance": "Names only; no value ever comes back. used_by lists the connections "
        "that name a secret; a script, routine or Skill may also read it by name, and "
        "nothing lists that. A secret a connection names is deleted only after the owner "
        "removes that connection. secret_delete needs the owner to name the secret.",
    }


def words(text: str) -> str:
    """Lower-case letters and digits in single-spaced words: _, - and spaces are alike."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


async def owner_named(session: AsyncSession, run: RunRow, message_id: str, name: str) -> bool:
    """Whether the owner's own words this Run answers name the secret: the message it
    started on, or one the owner added while it worked."""
    added = select(SteeringRow.message_id).where(SteeringRow.run_id == run.id)
    said = await session.scalars(
        select(MessageRow.content).where(
            MessageRow.thread_id == run.thread_id,
            MessageRow.role == "user",
            # The owner's own words only: never a card's send or a follow-up tap.
            MessageRow.origin == "owner",
            or_(MessageRow.id == message_id, MessageRow.id.in_(added)),
        )
    )
    return any(f" {words(name)} " in f" {words(text)} " for text in said)


async def delete(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = SecretDeleteInput.model_validate(args)
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        receipt = await session.get(EffectReceiptRow, context.effect_key)
        if receipt:
            return receipt.result  # A replayed call answers as it did.
        message_id = await owner_message_id(session, run)
        if message_id is None or not await owner_named(session, run, message_id, params.name):
            return {
                "ok": False,
                "code": "secret_delete_requires_owner_message",
                "deleted": False,
                "recovery": "Nothing was deleted. Only the owner removes a secret, by naming "
                f"it in a new message (for example: delete {params.name}). Tell him so and "
                "end your turn; do not wait for his reply in this Run.",
            }
        row = await session.scalar(
            select(SecretRow).where(
                SecretRow.owner_id == context.owner_id,
                SecretRow.scope == WORKSPACE,
                SecretRow.name == params.name,
            )
        )
        result: dict[str, Any] = {"ok": False, "code": "secret_not_found", "deleted": False}
        if row is not None:
            try:
                await delete_secret(session, context.owner_id, row.id)
                result = {"ok": True, "deleted": True, "name": params.name}
            except LonoraError as error:
                if error.code != "secret_in_use":
                    raise
                result = {
                    "ok": False,
                    "code": "secret_in_use",
                    "deleted": False,
                    "recovery": "Nothing was deleted. A connection names it: the owner "
                    "removes that connection first.",
                }
        session.add(EffectReceiptRow(key=context.effect_key, result=result))
        return result


def tools() -> list[Tool]:
    return [
        Tool(
            "secrets_list",
            "List the owner's saved workspace secrets by name, when each was saved and the "
            "connections that name it. Never a value. Use it when the owner asks what is "
            "saved.",
            SecretsListInput,
            listing,
            read_only=True,
            search_terms="keys tokens passwords credentials saved secrets "
            "مفاتيح أسرار كلمات مرور رموز",
        ),
        Tool(
            "secret_delete",
            "Delete one workspace secret when the owner's own words this Run answers name it "
            "(as secrets_list shows it). Refused otherwise, and for a secret a connection "
            "still names.",
            SecretDeleteInput,
            delete,
            replay_safe=True,
            search_terms="remove forget delete key token password secret "
            "احذف امسح مفتاح سر كلمة مرور",
        ),
    ]
