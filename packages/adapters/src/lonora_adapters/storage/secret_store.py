from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import SecretRow
from lonora_db.secrets import BROKER, require_scope, secret_in_use
from lonora_security.secrets import SecretCipher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def store_in_session(
    session: AsyncSession, cipher: SecretCipher, owner_id: str, name: str, value: str, scope: str
) -> str:
    require_scope(name, scope)
    row = await session.scalar(
        select(SecretRow)
        .where(SecretRow.owner_id == owner_id, SecretRow.scope == scope, SecretRow.name == name)
        .with_for_update()
    )
    if row:
        row.ciphertext = cipher.encrypt(value)
        row.updated_at = utcnow()
    else:
        row = SecretRow(owner_id=owner_id, scope=scope, name=name, ciphertext=cipher.encrypt(value))
        session.add(row)
        await session.flush()
    return row.id


class EncryptedSecretStore:
    """The owner's secrets of every scope except ``broker``.

    Broker values (7.2.3) are read and written only through ``BrokerSecrets``; this store,
    which every tool context carries, refuses them.
    """

    def __init__(self, db: Database, key: str, owner_id: str):
        self.db, self.cipher, self.owner_id = db, SecretCipher(key), owner_id

    async def read(self, secret_id: str) -> str:
        async with self.db.sessions() as session:
            row = await session.get(SecretRow, secret_id)
            if row is None or row.owner_id != self.owner_id:
                raise LonoraError("secret_not_found", 404)
            if row.scope == BROKER:
                raise LonoraError("secret_scope_forbidden", 403)
            return self.cipher.decrypt(row.ciphertext)

    async def write(self, name: str, value: str, scope: str) -> str:
        async with self.db.sessions() as session, session.begin():
            return await self.write_in_session(session, name, value, scope)

    async def write_in_session(
        self, session: AsyncSession, name: str, value: str, scope: str
    ) -> str:
        """Commit credentials with their resource; a rejected resource writes nothing."""
        if scope == BROKER:
            raise LonoraError("secret_scope_forbidden", 403)
        return await store_in_session(session, self.cipher, self.owner_id, name, value, scope)

    async def delete(self, secret_id: str) -> None:
        async with self.db.sessions() as session, session.begin():
            row = await session.get(SecretRow, secret_id, with_for_update=True)
            if row is None or row.owner_id != self.owner_id:
                raise LonoraError("secret_not_found", 404)
            if await secret_in_use(session, self.owner_id, secret_id):
                raise LonoraError("secret_in_use", 409)
            await session.delete(row)
