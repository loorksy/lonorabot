"""Live check of MetaApi provisioning on the owner's demo account (mandate 9.2, 9.4).

Run by the lead on the owner's server, inside the app's environment (LONORA_DATABASE_URL
and LONORA_ENCRYPTION_KEY set as for the API), against the production database:

    .venv/bin/python scripts/metaapi_provisioning_check.py
    .venv/bin/python scripts/metaapi_provisioning_check.py --probe-refusals

By default it only reads. With the owner's saved MetaApi token it lists the token's
accounts, and for every MetaApi connection it checks that provisioning finds the account
again from its login and server (what a connect from chat does, Q4) and reads MetaApi's
state and broker link (what proactive health reads).

``--probe-refusals`` also sends two account creations that MetaApi must refuse: a made-up
login with a made-up password on the demo account's own server (expected
``broker_password_rejected``), and the same on a server that does not exist (expected
``broker_server_not_found``). Neither can create an account. If MetaApi ever did create
one, the script removes it at once and says so.

It prints no secret, token, password, login, server name or account id: only counts,
states, yes/no and error codes.
"""

import argparse
import asyncio
import secrets
import sys
from typing import Any

from lonora_adapters.brokers.metaapi_provisioning import MetaApiProvisioning
from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_api.env import get_settings
from lonora_contracts.broker import BrokerConnection
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import current_broker_identity
from lonora_db.client import Database
from lonora_db.schema import BrokerSessionRow, OwnerRow
from lonora_db.secrets import METAAPI_TOKEN
from sqlalchemy import select


def say(line: str) -> None:
    print(line, flush=True)


async def probe(client: MetaApiProvisioning, *, server: str, platform: str, expected: str) -> bool:
    login = "9" + "".join(secrets.choice("0123456789") for _ in range(8))
    try:
        found, created = await client.find_or_create(
            login=login,
            server=server,
            platform=platform,
            password="lonora-probe-" + secrets.token_hex(8),
            request_key="lonora-probe-" + secrets.token_hex(8),
        )
    except LonoraError as failure:
        say(f"  refused with {failure.code} (expected {expected})")
        return failure.code == expected
    say(f"  NOT refused: MetaApi {'created' if created else 'found'} an account; removing it")
    if created:
        await client.remove(found.account_id)
        say("  removed")
    return False


async def check(probe_refusals: bool, owner: str | None = None) -> int:
    settings = get_settings()
    db = Database.connect(settings.database_url)
    failures = 0
    try:
        if owner is None:
            async with db.sessions() as session:
                owners = list(await session.scalars(select(OwnerRow.id)))
            if len(owners) != 1:
                say(f"expected one owner, found {len(owners)}")
                return 1
            owner = owners[0]
        broker = BrokerSecrets(db, settings.encryption_key.get_secret_value(), owner)
        async with db.sessions() as session:
            rows = [
                row
                for row in await session.scalars(
                    select(BrokerSessionRow).where(BrokerSessionRow.owner_id == owner)
                )
                if row.payload.get("provider") == "metaapi"
            ]
        say(f"MetaApi connections: {len(rows)}")
        token_id = await broker.named(METAAPI_TOKEN)
        if token_id is None and rows:
            token_id = BrokerConnection.model_validate(rows[0].payload).secret_id
        say(
            f"owner token saved as {METAAPI_TOKEN}: {'yes' if await broker.named(METAAPI_TOKEN) else 'no'}"
        )
        if token_id is None:
            say("no MetaApi token: nothing to check")
            return 1
        client = MetaApiProvisioning(await broker.read(token_id))
        try:
            accounts = await client.accounts()
            say(f"accounts visible to the token: {len(accounts)}")
            say(f"default region known: {'yes' if await client.default_region() else 'no'}")
            demo: dict[str, Any] | None = None
            for index, row in enumerate(rows, start=1):
                identity = current_broker_identity(row) or {}
                config = BrokerConnection.model_validate(row.payload)
                if not identity.get("login") or not identity.get("server"):
                    say(f"connection {index}: no observed identity on record")
                    failures += 1
                    continue
                found = await client.find(str(identity["login"]), str(identity["server"]))
                same = found is not None and found.account_id == config.account_id
                state = await client.state(config.account_id)
                say(
                    f"connection {index}: found again by login and server: "
                    f"{'yes' if found else 'no'}; the same MetaApi account: {'yes' if same else 'no'}; "
                    f"state {state.state}; broker link {state.connection_status}"
                )
                failures += 0 if same else 1
                demo = demo or {
                    "server": str(identity["server"]),
                    "platform": str(identity.get("platform") or "mt5"),
                }
            if probe_refusals:
                if demo is None:
                    say("refusal probes skipped: no connection with an observed identity")
                    failures += 1
                else:
                    say("probe: wrong password on the demo account's server")
                    failures += (
                        0 if await probe(client, expected="broker_password_rejected", **demo) else 1
                    )
                    say("probe: a server that does not exist")
                    failures += (
                        0
                        if await probe(
                            client,
                            expected="broker_server_not_found",
                            server="Lonora-NoSuchServer-" + secrets.token_hex(4),
                            platform=demo["platform"],
                        )
                        else 1
                    )
        finally:
            await client.close()
    finally:
        await db.close()
    say("OK" if not failures else f"FAILED ({failures})")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--probe-refusals", action="store_true")
    sys.exit(asyncio.run(check(parser.parse_args().probe_refusals)))


if __name__ == "__main__":
    main()
