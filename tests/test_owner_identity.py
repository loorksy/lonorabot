"""«الاسم» and «طريقة المخاطبة» (WP-H): saved as an attributed preference change, logged
field by field, restorable, and other preferences stay as they are."""

import os
from typing import Any, cast

import pytest


@pytest.mark.asyncio
async def test_name_and_address_save_log_and_restore():
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Uses the migrated PostgreSQL schema.")
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        before = await fixture.request("GET", "/owner/profile")
        language = before["reply_language"]
        saved = await fixture.request(
            "PUT", "/owner/preferences", {"name": "  أحمد  ", "address": "أبو خالد"}
        )
        assert saved["name"] == "أحمد" and saved["address"] == "أبو خالد"
        assert saved["reply_language"] == language
        assert saved["reach_me"]["channel"] == before["reach_me"]["channel"]
        await fixture.request("PUT", "/owner/preferences", {"name": "أحمد سالم"})
        revisions = await fixture.request("GET", "/owner/profile/revisions?limit=5")
        latest = cast("list[dict[str, Any]]", revisions)[0]
        fields = {item["field"]: item for item in latest["changes"]}
        assert fields["name"] == {"field": "name", "before": "أحمد", "after": "أحمد سالم"}
        assert "address" not in fields
        await fixture.request("POST", f"/memory/revisions/{latest['id']}/revert", {})
        profile = await fixture.request("GET", "/owner/profile")
        assert profile["name"] == "أحمد" and profile["address"] == "أبو خالد"
        # Saving only the reach-me policy keeps the reply language (only sent fields change).
        await fixture.request("PUT", "/owner/preferences", {"reply_language": "ar"})
        policy = (await fixture.request("GET", "/owner/profile"))["reach_me"]
        policy.pop("enabled", None)
        kept = await fixture.request("PUT", "/owner/preferences", {"reach_me": policy})
        assert kept["reply_language"] == "ar", kept
        cleared = await fixture.request("PUT", "/owner/preferences", {"name": "", "address": None})
        assert cleared["name"] is None and cleared["address"] is None
    finally:
        await fixture.close()
