"""Every secret value given to a workspace command, kept encrypted for a while (7.2.6).

A log on the workspace disk, or a process started before a rotation, can still hold a
value that is no longer stored. The scan of workspace output covers these values too, for
KEPT after they were last given, across restarts. They are encrypted with the same key as
the secret store, and never written to the workspace disk.
"""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from lonora_security.secrets import SecretCipher
from sqlalchemy import delete, select

from .client import Database
from .schema import WorkspaceGivenRow

KEPT = timedelta(days=30)


def digest(key: str, owner_id: str, name: str, value: str) -> str:
    """Keyed, so a copy of the database without the key confirms no guessed value."""
    message = "\0".join(("workspace_given", owner_id, name, value)).encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


class GivenValues:
    def __init__(self, db: Database, key: str, owner_id: str):
        self.db, self.cipher, self.owner_id = db, SecretCipher(key), owner_id
        self.key = key

    async def record(self, values: dict[str, str]) -> None:
        if not values:
            return
        now = datetime.now(UTC)
        async with self.db.sessions() as session, session.begin():
            for name, value in values.items():
                key = digest(self.key, self.owner_id, name, value)
                row = await session.scalar(
                    select(WorkspaceGivenRow).where(
                        WorkspaceGivenRow.owner_id == self.owner_id,
                        WorkspaceGivenRow.digest == key,
                    )
                )
                if row is None:
                    session.add(
                        WorkspaceGivenRow(
                            owner_id=self.owner_id,
                            name=name,
                            digest=key,
                            ciphertext=self.cipher.encrypt(value),
                            given_at=now,
                        )
                    )
                else:
                    row.given_at = now

    async def values(self) -> list[tuple[str, str]]:
        cutoff = datetime.now(UTC) - KEPT
        async with self.db.sessions() as session, session.begin():
            await session.execute(
                delete(WorkspaceGivenRow).where(
                    WorkspaceGivenRow.owner_id == self.owner_id,
                    WorkspaceGivenRow.given_at < cutoff,
                )
            )
            rows = (
                await session.scalars(
                    select(WorkspaceGivenRow).where(WorkspaceGivenRow.owner_id == self.owner_id)
                )
            ).all()
            return [(row.name, self.cipher.decrypt(row.ciphertext)) for row in rows]
