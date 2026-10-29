from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import SecretRow
from lonora_security.secrets import SecretCipher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class EncryptedSecretStore:
    def __init__(self, db: Database, key: str, owner_id: str):
        self.db, self.cipher, self.owner_id = db, SecretCipher(key), owner_id

    async def read(self, secret_id: str) -> str:
        async with self.db.sessions() as session:
            row = await session.get(SecretRow, secret_id)
            if row is None or row.owner_id != self.owner_id:
                raise LonoraError("secret_not_found", 404)
            return self.cipher.decrypt(row.ciphertext)

    async def write(self, name: str, value: str, scope: str) -> str:
        async with self.db.sessions() as session, session.begin():
            return await self.write_in_session(session, name, value, scope)

    async def write_in_session(
        self, session: AsyncSession, name: str, value: str, scope: str
    ) -> str:
        """Commit credentials with their resource; a rejected resource writes nothing."""
        row = await session.scalar(
            select(SecretRow)
            .where(
                SecretRow.owner_id == self.owner_id,
                SecretRow.scope == scope,
                SecretRow.name == name,
            )
            .with_for_update()
        )
        if row:
            row.ciphertext = self.cipher.encrypt(value)
            row.updated_at = utcnow()
        else:
            row = SecretRow(
                owner_id=self.owner_id,
                scope=scope,
                name=name,
                ciphertext=self.cipher.encrypt(value),
            )
            session.add(row)
            await session.flush()
        return row.id

    async def delete(self, secret_id: str) -> None:
        async with self.db.sessions() as session, session.begin():
            row = await session.get(SecretRow, secret_id, with_for_update=True)
            if row is None or row.owner_id != self.owner_id:
                raise LonoraError("secret_not_found", 404)
            await session.delete(row)
