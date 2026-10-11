"""Administrative commands for local-owner Lonora instances."""

import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select, update

from .auth import hash_password
from .config import get_settings
from .database import create_database
from .orm import AgentRow, UserRow


async def create_user(email: str, password: str) -> None:
    settings = get_settings()
    normalized_email = email.strip().lower()
    if len(normalized_email) > 254 or "@" not in normalized_email:
        raise SystemExit("invalid_email")
    if not 12 <= len(password) <= 128:
        raise SystemExit("invalid_password_length")
    engine, sessions = create_database(settings.database_url)
    try:
        async with sessions() as session, session.begin():
            existing = await session.scalar(
                select(UserRow.id).where(UserRow.email == normalized_email)
            )
            if existing is not None:
                raise SystemExit("user_already_exists")
            user = UserRow(email=normalized_email, password_hash=hash_password(password))
            session.add(user)
            await session.flush()
            await session.execute(
                update(AgentRow).where(AgentRow.owner_id.is_(None)).values(owner_id=user.id)
            )
    finally:
        await engine.dispose()
    print("user_created")


def main() -> None:
    parser = argparse.ArgumentParser(prog="lonora-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    add_user = commands.add_parser("create-user")
    add_user.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass("Password (12+ characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 12 or password != confirmation:
        raise SystemExit("invalid_password_confirmation")
    asyncio.run(create_user(args.email, password))


if __name__ == "__main__":
    main()
