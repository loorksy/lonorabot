"""The broker destination of 7.2.3: the MetaApi token and broker account passwords.

Scope ``broker`` is read and written only here. Only the broker adapter layer
(``BrokerManager``) and MetaApi connection and provisioning code construct this class.
The general ``EncryptedSecretStore``, which tool contexts carry, refuses the scope, so no
tool result, workspace command, log or message can carry a broker value.
"""

from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import SecretRow
from lonora_db.secrets import BROKER
from lonora_security.secrets import SecretCipher
from sqlalchemy.ext.asyncio import AsyncSession

from .secret_store import store_in_session


class BrokerSecrets:
    def __init__(self, db: Database, key: str, owner_id: str):
        self._db, self._cipher, self._owner_id = db, SecretCipher(key), owner_id

    async def read(self, secret_id: str) -> str:
        async with self._db.sessions() as session:
            row = await session.get(SecretRow, secret_id)
            if row is None or row.owner_id != self._owner_id:
                raise LonoraError("secret_not_found", 404)
            if row.scope != BROKER:
                raise LonoraError("secret_scope_forbidden", 403)
            return self._cipher.decrypt(row.ciphertext)

    async def write_in_session(self, session: AsyncSession, name: str, value: str) -> str:
        """Commit a broker value with its connection; a rejected connection writes nothing."""
        return await store_in_session(session, self._cipher, self._owner_id, name, value, BROKER)
