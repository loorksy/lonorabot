"""Lonora Cloud: one sign-up (docs/cloud/DECISIONS.md D48).

The website account that asked for an installation becomes its owner with the password it signed
up with, so the customer never registers twice. The installation accepts the website's stored hash
and replaces it with its own on the first sign-in.
"""

from typing import Any

import pytest
from lonora_core.user_error import LonoraError

# Made by cloud/site/functions/_lib/core.js hashPassword("lonora-site-password-1").
SITE_PASSWORD = "lonora-site-password-1"
SITE_HASH = (
    "pbkdf2-sha256$100000$5e7f5f4bc7ed5b7a76da1a3e398ff396"
    "$5319fb67bdab3c28680b30b5963f1148c3ea9dc9d7325b4d2fd352a16c001b26"
)
# The website takes passwords of 10 characters: hashPassword("Market2024").
SHORT_PASSWORD = "Market2024"
SHORT_HASH = (
    "pbkdf2-sha256$100000$e3b6f6f16b8a013f2d95f2a39fc52efd"
    "$42879fef5c455ce04ef9c6f805bd51eac6b6c212d0d304300831070ffd18f935"
)


def test_the_websites_hash_signs_in_and_is_replaced_by_this_servers_own() -> None:
    from lonora_auth.account_security import kept_hash, verify_password

    assert verify_password(SITE_PASSWORD, SITE_HASH)
    assert not verify_password(SITE_PASSWORD + "x", SITE_HASH)
    assert not verify_password(SITE_PASSWORD, SITE_HASH.replace("$100000$", "$100001$"))
    own = kept_hash(SITE_PASSWORD, SITE_HASH)
    assert not own.startswith("pbkdf2-sha256$") and verify_password(SITE_PASSWORD, own)
    assert kept_hash(SITE_PASSWORD, own) == own  # this server's own hash is kept as it is


@pytest.mark.asyncio
async def test_only_a_website_hash_is_imported_and_only_while_there_is_no_owner() -> None:
    from check_streaming import Fixture
    from lonora_auth.owner_policy import import_owner

    fixture = await Fixture().open()  # the shared test database already has its owner
    try:
        async with fixture.runtime.db.sessions() as session:
            with pytest.raises(LonoraError) as plain:
                await import_owner(session, "new@example.com", "plain-password-not-a-hash")
            assert plain.value.code == "invalid_password"
            with pytest.raises(LonoraError) as taken:
                await import_owner(session, "new@example.com", SITE_HASH)
            assert taken.value.code == "owner_already_initialized"
    finally:
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("site_password", "site_hash"), [(SITE_PASSWORD, SITE_HASH), (SHORT_PASSWORD, SHORT_HASH)]
)
async def test_the_owner_signs_in_with_the_website_password_once_imported(
    site_password: str, site_hash: str
) -> None:
    from check_streaming import Fixture
    from lonora_db.owner import get_owner

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            owner: Any = await get_owner(session)
            assert owner is not None
            email, before = owner.email, owner.password_hash
            owner.password_hash = site_hash  # as customer.sh create imports it
        try:
            wrong = await fixture.client.post(
                "/api/auth/login", json={"email": email, "password": site_password + "x"}
            )
            assert wrong.status_code == 401
            signed_in = await fixture.client.post(
                "/api/auth/login", json={"email": email, "password": site_password}
            )
            assert signed_in.status_code == 200, signed_in.text
            async with fixture.runtime.db.sessions() as session:
                stored = (await get_owner(session)).password_hash  # type: ignore[union-attr]
            assert not stored.startswith("pbkdf2-sha256$")
            again = await fixture.client.post(
                "/api/auth/mobile/login", json={"email": email, "password": site_password}
            )
            assert again.status_code == 200, again.text
        finally:
            async with fixture.runtime.db.sessions() as session, session.begin():
                restored: Any = await get_owner(session)
                restored.password_hash = before
    finally:
        await fixture.close()
