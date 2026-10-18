"""Authenticated global budgeting configuration against disposable PostgreSQL."""

import asyncio

import httpx
from check_streaming import Fixture
from lonora_contracts.model_context import ModelContextPolicy
from lonora_db.transactions import SettingsRepository


async def checks() -> None:
    fixture = await Fixture().open()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(fixture.app), base_url="https://streaming.test"
        ) as anonymous:
            assert (await anonymous.get("/api/settings/models/context")).status_code == 401
            denied = await anonymous.put(
                "/api/settings/models/context", json=ModelContextPolicy().model_dump()
            )
            assert denied.status_code in {401, 403}
        default = await fixture.request("GET", "/settings/models/context")
        assert default == ModelContextPolicy().model_dump()
        desired = {**default, "output_tokens": 2048, "maximum_input_tokens": 48000}
        assert await fixture.request("PUT", "/settings/models/context", desired) == desired
        assert await fixture.request("GET", "/settings/models/context") == desired
        for invalid in ({**desired, "output_tokens": 0}, {**desired, "provider": "openai"}):
            response = await fixture.client.put("/api/settings/models/context", json=invalid)
            assert response.status_code == 422
        async with fixture.runtime.db.sessions() as session:
            stored = await SettingsRepository().get(session, "model_context")
            assert stored == desired
        assert await fixture.request("GET", "/settings/models/context") == desired
        print(
            "PASS owner-only global context policy, durable roundtrip, bounded fields and no per-Agent model settings"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(checks())
