"""The owner's workspace secrets from chat (VISION.md P5, 7.2.4).

The owner asks in chat which secrets are saved, and removes one in his own words. A
value never comes back: only names, when each was saved, and the connections that use
it. Deleting goes through the one deletion of a stored secret (``delete_secret``), the
same as ``DELETE /secrets/{secret_id}``, which stays the only route that deletes one
(14.3.11). Only the owner's typed message this Run answers can ask for it, and a secret
a connection uses is not deleted.
"""

from typing import Any

from lonora_contracts.agent_secrets import WORKSPACE_SECRET_NAME
from lonora_contracts.domain import Contract
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, SecretRow
from lonora_db.secrets import WORKSPACE, delete_secret, secret_in_use, workspace_secrets
from pydantic import Field
from sqlalchemy import select

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
        "guidance": "Names only; no value ever comes back. A secret a connection uses "
        "(used_by) can be deleted only after the owner removes that connection. Delete one "
        "with secret_delete only when the owner asks in his own words.",
    }


async def delete(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = SecretDeleteInput.model_validate(args)
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        receipt = await session.get(EffectReceiptRow, context.effect_key)
        if receipt:
            return receipt.result  # A replayed call answers as it did.
        if await owner_message_id(session, run) is None:
            return {
                "ok": False,
                "code": "secret_delete_requires_owner_message",
                "deleted": False,
                "recovery": "Nothing was deleted. Only the owner removes a secret: ask him to "
                "say so in chat.",
            }
        row = await session.scalar(
            select(SecretRow).where(
                SecretRow.owner_id == context.owner_id,
                SecretRow.scope == WORKSPACE,
                SecretRow.name == params.name,
            )
        )
        if row is None:
            result: dict[str, Any] = {"ok": False, "code": "secret_not_found", "deleted": False}
        elif await secret_in_use(session, context.owner_id, row.id):
            result = {
                "ok": False,
                "code": "secret_in_use",
                "deleted": False,
                "recovery": "Nothing was deleted. A connection uses it: the owner removes "
                "that connection first.",
            }
        else:
            await delete_secret(session, context.owner_id, row.id)
            result = {"ok": True, "deleted": True, "name": params.name}
        session.add(EffectReceiptRow(key=context.effect_key, result=result))
        return result


def tools() -> list[Tool]:
    return [
        Tool(
            "secrets_list",
            "List the owner's saved workspace secrets by name, when each was saved and the "
            "connections that use it. Never a value. Use it when the owner asks what is "
            "saved.",
            SecretsListInput,
            listing,
            read_only=True,
            search_terms="keys tokens passwords credentials saved secrets "
            "مفاتيح أسرار كلمات مرور رموز",
        ),
        Tool(
            "secret_delete",
            "Delete one workspace secret by name when the owner asks in his own words this "
            "Run answers. Refused without his message, and for a secret a connection still "
            "uses.",
            SecretDeleteInput,
            delete,
            replay_safe=True,
            search_terms="remove forget delete key token password secret "
            "احذف امسح مفتاح سر كلمة مرور",
        ),
    ]
