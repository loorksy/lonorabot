"""One-off: carry the owner's provider keys and MetaApi credential from the old Lonora into a fresh install.

Run inside the NEW api container (same LONORA_ENCRYPTION_KEY as the old install, copied by --env-from):
    python import_secrets.py /tmp/lonora-secret-export.json
Prints names and outcomes only, never a value. Provider keys go through the app's own secret store;
the broker account goes through connect_account (the same path as the Connect screen), which verifies
it with MetaApi, and is created disabled so the owner turns it on.
"""

import asyncio
import json
import sys

from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_api.env import Settings
from lonora_contracts.broker import BrokerConnection
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import OwnerRow
from lonora_providers.registry import PROVIDERS
from lonora_security.secrets import SecretCipher
from lonora_trading import connections
from sqlalchemy import select


async def main(path: str) -> int:
    with open(path) as handle:
        data = json.load(handle)
    settings = Settings()
    key = settings.encryption_key.get_secret_value()
    cipher = SecretCipher(key)
    db = Database.connect(settings.database_url)
    failed = 0
    try:
        async with db.sessions() as session:
            owners = list((await session.scalars(select(OwnerRow.id))).all())
        if len(owners) != 1:
            print(f"STOP: expected exactly one owner account, found {len(owners)}. Create the owner account first.")
            return 2
        store = EncryptedSecretStore(db, key, owners[0])
        rows = {row["id"]: row for row in data.get("secrets") or []}
        for row in rows.values():
            label = f"{row['scope']}/{row['name']}"
            if row["scope"] != "provider":
                continue
            if row["name"] not in PROVIDERS:
                print(f"skipped {label}: provider not known to this version")
                continue
            try:
                await store.write(row["name"], cipher.decrypt(row["ciphertext"]), "provider")
                print(f"imported {label}")
            except LonoraError as error:
                failed += 1
                print(f"FAILED {label}: {error.code}")
        used = set()
        for payload in data.get("brokers") or []:
            secret = rows.get(payload.get("secret_id") or "")
            account = str(payload.get("account_id") or "")
            label = f"broker {payload.get('provider')} account {account[:8]}..."
            if payload.get("provider") != "metaapi" or secret is None:
                print(f"skipped {label}: not a MetaApi account with a stored credential")
                continue
            used.add(secret["id"])
            config = BrokerConnection(
                provider="metaapi", account_id=account, region=payload.get("region"), enabled=False
            )
            try:
                await connections.connect_account(
                    db, store, owners[0], config, cipher.decrypt(secret["ciphertext"])
                )
                print(f"imported {label} (verified with MetaApi, left disabled)")
            except LonoraError as error:
                if error.code == "broker_account_already_connected":
                    print(f"already present {label}")
                    continue
                failed += 1
                print(f"FAILED {label}: {error.code}")
        for row in rows.values():
            if row["scope"] not in ("provider",) and row["id"] not in used:
                print(f"skipped {row['scope']}/{row['name']}: no matching record to attach it to")
    finally:
        await db.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
