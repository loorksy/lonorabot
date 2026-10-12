import argparse
import asyncio
import getpass

import uvicorn
from lonora_auth.account_security import hash_password, normalize_email
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.owner import get_owner
from lonora_db.schema import OwnerRow

from .app import create_app
from .env import get_settings

app = create_app()


async def create_owner(email: str) -> None:
    db = Database.connect(get_settings().database_url)
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        raise LonoraError("password_mismatch")
    try:
        async with db.sessions() as session, session.begin():
            if await get_owner(session):
                raise LonoraError("owner_already_initialized", 409)
            session.add(
                OwnerRow(email=normalize_email(email), password_hash=hash_password(password))
            )
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="lonora-api")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--create-owner")
    args = parser.parse_args()
    if args.create_owner:
        asyncio.run(create_owner(args.create_owner))
        return
    uvicorn.run("lonora_api.server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
