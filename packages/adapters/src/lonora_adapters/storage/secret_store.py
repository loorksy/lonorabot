from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import SecretRow
from lonora_db.secrets import BROKER, WORKSPACE, delete_secret, require_scope
from lonora_security.secrets import SHORTEST_SECRET, SecretCipher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def encrypt_in_session(
    session: AsyncSession, cipher: SecretCipher, owner_id: str, name: str, value: str, scope: str
) -> str:
    """Upsert one encrypted value. The caller decides the scope: only the two stores call
    it, and the general store never with ``broker``."""
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

    async def workspace_values(self) -> dict[str, str]:
        """Every workspace secret by name: what agents use by name in the workspace
        (VISION.md 7.2.4, 7.2.5). Only the workspace scope: a broker, provider or
        integration value never comes out."""
        async with self.db.sessions() as session:
            rows = (
                await session.scalars(
                    select(SecretRow).where(
                        SecretRow.owner_id == self.owner_id, SecretRow.scope == WORKSPACE
                    )
                )
            ).all()
        return {row.name: self.cipher.decrypt(row.ciphertext) for row in rows}

    async def scanned_values(self) -> dict[str, str]:
        """Every stored value the scan of workspace output replaces, by the name its
        marker shows (VISION.md 7.2.6): the workspace, integration and provider scopes.
        Not the broker scope: only the execution door and provisioning read it (7.2.3),
        and neither sends bytes back through the workspace. A name another scope already
        holds is shown with its scope (``integration:NAME``), so no value is dropped."""
        async with self.db.sessions() as session:
            rows = (
                await session.scalars(
                    select(SecretRow)
                    .where(SecretRow.owner_id == self.owner_id, SecretRow.scope != BROKER)
                    .order_by(SecretRow.scope != WORKSPACE, SecretRow.scope, SecretRow.name)
                )
            ).all()
        values: dict[str, str] = {}
        for row in rows:
            name = row.name if row.name not in values else row.scope + ":" + row.name
            values[name] = self.cipher.decrypt(row.ciphertext)
        return values

    async def write(self, name: str, value: str, scope: str) -> str:
        async with self.db.sessions() as session, session.begin():
            return await self.write_in_session(session, name, value, scope)

    async def write_in_session(
        self, session: AsyncSession, name: str, value: str, scope: str
    ) -> str:
        """Commit credentials with their resource; a rejected resource writes nothing."""
        if scope == BROKER:
            # Broker values are written only through ``BrokerSecrets`` (7.2.3).
            raise LonoraError("secret_scope_forbidden", 403)
        require_scope(name, scope)
        if len(value) < SHORTEST_SECRET:
            # Workspace output is scanned for every value outside the broker scope; a
            # shorter value cannot be found there.
            # Three characters are at least three bytes.
            raise LonoraError("secret_value_too_short", 422)
        return await encrypt_in_session(session, self.cipher, self.owner_id, name, value, scope)

    async def delete(self, secret_id: str) -> None:
        async with self.db.sessions() as session, session.begin():
            await delete_secret(session, self.owner_id, secret_id)
