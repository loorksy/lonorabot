"""MetaApi provisioning: account-entity calls only, one account per login and server,
errors mapped to codes, and no credential in any diagnostic, log or traceback."""

import importlib
import inspect
import json
import logging
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from lonora_adapters.brokers import metaapi_provisioning
from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_adapters.brokers.metaapi_provisioning import MetaApiProvisioning
from lonora_core.user_error import LonoraError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.agent_eval.broker import FakeMetaApiProvisioning, FakeProvisioningApi  # noqa: E402

LOGIN, SERVER, PASSWORD = "50000001", "Exness-MT5Trial16", "fixture-master-password"
TOKEN = "fixture.metaapi.token"  # an API token is a JWT: three dot-separated parts


def client(api: FakeProvisioningApi) -> MetaApiProvisioning:
    return FakeMetaApiProvisioning(api, TOKEN)


def no_credential(text: str) -> None:
    for value in (PASSWORD, TOKEN, LOGIN, "wrong-fixture-password"):
        assert value not in text


@pytest.mark.asyncio
async def test_first_connect_creates_one_account_with_the_recorded_defaults() -> None:
    api = FakeProvisioningApi()
    account, created = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    assert created and account.login == LOGIN and account.server == SERVER
    assert account.platform == "mt5" and account.state == "DEPLOYED"  # read back after create
    assert api.creates == [
        {
            "login": LOGIN,
            "server": SERVER,
            "platform": "mt5",
            "name": "Lonora " + SERVER,
            "magic": 0,
            "reliability": "regular",
            "type": "cloud-g2",
        }
    ]
    assert api.accounts[account.account_id]["password"] == PASSWORD
    again, created_again = await client(api).find_or_create(
        login=LOGIN,
        server=SERVER.upper(),
        platform="mt5",
        password=PASSWORD,
        request_key="fixture-request",
    )
    assert not created_again and again.account_id == account.account_id
    assert api.calls.count("create_account") == 1 and len(api.accounts) == 1


@pytest.mark.asyncio
async def test_a_new_account_takes_the_region_of_the_tokens_existing_account() -> None:
    api = FakeProvisioningApi()
    api.servers["Other-Server"] = {"7001": "other-fixture-password"}
    api.link("7001", "Other-Server", region="singapore")
    account, created = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    assert created and account.region == "singapore"
    assert api.creates[-1]["region"] == "singapore"


@pytest.mark.asyncio
async def test_a_lost_create_answer_finds_the_account_instead_of_a_second_one() -> None:
    api = FakeProvisioningApi(lose_create_answer="after_commit")
    account, created = await client(api).find_or_create(
        login=" " + LOGIN + " ",
        server=SERVER,
        platform="mt5",
        password=PASSWORD,
        request_key="fixture-request",
    )
    assert created and list(api.accounts) == [account.account_id]
    assert api.calls.count("create_account") == 1 and api.creates[0]["login"] == LOGIN
    again, created_again = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    assert not created_again and again.account_id == account.account_id


@pytest.mark.asyncio
async def test_a_create_lost_before_metaapi_saw_it_fails_and_the_retry_creates_one() -> None:
    api = FakeProvisioningApi(lose_create_answer="before_commit")
    with pytest.raises(LonoraError) as lost:
        await client(api).find_or_create(
            login=LOGIN,
            server=SERVER,
            platform="mt5",
            password=PASSWORD,
            request_key="fixture-request",
        )
    assert lost.value.code == "broker_provisioning_unavailable" and api.accounts == {}
    account, created = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    assert created and list(api.accounts) == [account.account_id]
    assert "login" not in repr(account) and LOGIN not in repr(account)


@pytest.mark.asyncio
async def test_an_owner_linked_account_is_reused_deployed_one_first() -> None:
    api = FakeProvisioningApi()
    stopped = api.link(LOGIN, SERVER, deployed=False)
    running = api.link(LOGIN, SERVER)
    api.servers["Exness-MT5Trial17"] = {LOGIN: PASSWORD}
    api.link(LOGIN, "Exness-MT5Trial17")
    found = await client(api).find(LOGIN, SERVER)
    assert found is not None and found.account_id == running != stopped
    assert found.deployed and found.connected
    account, created = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    assert not created and account.account_id == running
    assert "create_account" not in api.calls
    assert await client(api).find("5000000", SERVER) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "server,password,token_valid,code",
    [
        (SERVER, "wrong-fixture-password", True, "broker_password_rejected"),
        ("Exness-Unknown", PASSWORD, True, "broker_server_not_found"),
        (SERVER, PASSWORD, False, "broker_token_rejected"),
    ],
)
async def test_refusals_are_mapped_and_carry_no_credential(
    caplog: pytest.LogCaptureFixture, server: str, password: str, token_valid: bool, code: str
) -> None:
    api = FakeProvisioningApi(token_valid=token_valid)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(LonoraError) as refused:
        await client(api).find_or_create(
            login=LOGIN,
            server=server,
            platform="mt5",
            password=password,
            request_key="fixture-request",
        )
    assert refused.value.code == code and api.accounts == {}
    assert refused.value.__cause__ is None and refused.value.__suppress_context__
    no_credential(str(refused.value.diagnostic_message))
    no_credential(caplog.text)


@pytest.mark.asyncio
async def test_platform_is_required() -> None:
    api = FakeProvisioningApi()
    with pytest.raises(LonoraError) as refused:
        await client(api).find_or_create(
            login=LOGIN,
            server=SERVER,
            platform="",
            password=PASSWORD,
            request_key="fixture-request",
        )
    assert refused.value.code == "broker_platform_required" and api.calls == []


@pytest.mark.asyncio
async def test_lifecycle_reports_state_and_broker_connection_status() -> None:
    api = FakeProvisioningApi()
    provisioning = client(api)
    account, _ = await provisioning.find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    deployed = await provisioning.deploy(account.account_id)
    assert deployed.deployed and deployed.connected
    stored = await provisioning.update_password(account.account_id, "wrong-fixture-password")
    assert api.updates == [{"name": "Lonora " + SERVER, "server": SERVER, "magic": 0}]
    assert stored.connected  # the terminal uses a new password only after a redeploy
    rotated = await provisioning.redeploy(account.account_id)
    assert rotated.deployed and rotated.connection_status == "DISCONNECTED_FROM_BROKER"
    await provisioning.update_password(account.account_id, PASSWORD)
    assert (await provisioning.redeploy(account.account_id)).connected
    undeployed = await provisioning.undeploy(account.account_id)
    assert undeployed.state == "UNDEPLOYED" and undeployed.connection_status == "DISCONNECTED"
    assert (await provisioning.state(account.account_id)).state == "UNDEPLOYED"
    await provisioning.remove(account.account_id)
    assert api.accounts == {}
    with pytest.raises(LonoraError) as missing:
        await provisioning.state(account.account_id)
    assert missing.value.code == "broker_account_not_found"


@pytest.mark.asyncio
async def test_a_password_update_keeps_an_owner_linked_accounts_settings() -> None:
    api = FakeProvisioningApi()
    linked = api.link(LOGIN, SERVER)
    await client(api).update_password(linked, PASSWORD)
    assert api.updates == [
        {
            "name": "owner linked",
            "server": SERVER,
            "magic": 123456,
            "slippage": 2.5,
            "tags": ["owner"],
        }
    ]
    assert api.accounts[linked]["magic"] == 123456 and api.accounts[linked]["tags"] == ["owner"]


@pytest.mark.asyncio
async def test_the_client_never_opens_a_terminal_connection_or_trades() -> None:
    api = FakeProvisioningApi()
    account, _ = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    for forbidden in ("get_rpc_connection", "get_streaming_connection", "update"):
        with pytest.raises(LonoraError) as refused:
            await client(api)._act(account.account_id, forbidden)  # pyright: ignore[reportPrivateUsage]
        assert refused.value.code == "broker_provisioning_call_forbidden"
    source = inspect.getsource(metaapi_provisioning)
    for name in (
        "get_rpc_connection",
        "get_streaming_connection",
        "create_market",
        "MetaApiBroker(",
    ):
        assert name not in source


class Scripted:
    """The SDK's own HttpClient above a scripted transport: real error conversion."""

    def __init__(self, *answers: httpx.Response):
        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []

    async def __call__(self, options: dict[str, Any]) -> httpx.Response:
        self.requests.append(options)
        answer = self.answers.pop(0)
        answer.request = httpx.Request(options.get("method", "GET"), options["url"])
        return answer


def scripted(provisioning: MetaApiProvisioning, transport: Scripted) -> None:
    account_client = provisioning.api.metatrader_account_api._metatrader_account_client
    account_client._http_client._make_request = transport


def created(account_id: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "_id": account_id,
            "login": LOGIN,
            "server": SERVER,
            "version": 5,
            "region": "new-york",
            "state": "DEPLOYING",
            "connectionStatus": "DISCONNECTED",
        },
    )


@pytest.mark.asyncio
async def test_real_sdk_instance_keeps_trading_options_and_never_repeats_a_create(
    caplog: pytest.LogCaptureFixture,
) -> None:
    http_module: Any = importlib.import_module("metaapi_cloud_sdk.clients.http_client")
    trading = MetaApiBroker("fixture-provider-account", None, "fixture.trading.token")
    patched = http_module.HttpClient._make_request
    provisioning = MetaApiProvisioning(TOKEN)
    assert http_module.HttpClient._make_request is patched
    trading_http = trading.api.metatrader_account_api._metatrader_account_client._http_client
    assert trading_http._retries == 0 and trading_http._timeout == 20
    own = provisioning.api.metatrader_account_api._metatrader_account_client._http_client
    assert own is not trading_http and own._retries == 0
    caplog.set_level(logging.DEBUG)

    # A wrong password whose answer echoes the request; only the code is read.
    echo = [{"parameter": "password", "value": PASSWORD, "code": "E_AUTH"}]
    message = f"Login {LOGIN} with password {PASSWORD} failed, token={TOKEN}"
    transport = Scripted(
        httpx.Response(200, json=[]),
        httpx.Response(200, json=[]),
        httpx.Response(400, json={"error": "ValidationError", "message": message, "details": echo}),
    )
    scripted(provisioning, transport)
    with pytest.raises(LonoraError) as refused:
        await provisioning.find_or_create(
            login=LOGIN,
            server=SERVER,
            platform="mt5",
            password=PASSWORD,
            request_key="fixture-request",
        )
    assert refused.value.code == "broker_password_rejected"
    assert [request["method"] for request in transport.requests] == ["GET", "GET", "POST"]
    assert transport.requests[-1]["body"]["password"] == PASSWORD
    assert transport.requests[-1]["url"].startswith("https://mt-provisioning-api-v1.")
    no_credential(str(refused.value.diagnostic_message) + caplog.text)

    # The code as a plain string, and as a dict.
    for details, code in (
        ("E_SRV_NOT_FOUND", "broker_server_not_found"),
        ({"code": "E_AUTH"}, "broker_password_rejected"),
        ("E_SERVER_TIMEZONE", "broker_provisioning_rejected"),
    ):
        scripted(
            provisioning,
            Scripted(
                httpx.Response(200, json=[]),
                httpx.Response(200, json=[]),
                httpx.Response(400, json={"message": "Refused", "details": details}),
            ),
        )
        with pytest.raises(LonoraError) as mapped:
            await provisioning.find_or_create(
                login=LOGIN,
                server=SERVER,
                platform="mt5",
                password=PASSWORD,
                request_key="fixture-request",
            )
        assert mapped.value.code == code

    # A server error on create is not retried: a retry would be a second account.
    transport = Scripted(
        httpx.Response(200, json=[]),
        httpx.Response(200, json=[]),
        httpx.Response(500, json={"error": "InternalError", "message": "boom"}),
        httpx.Response(200, json=[]),
    )
    scripted(provisioning, transport)
    with pytest.raises(LonoraError) as failed:
        await provisioning.find_or_create(
            login=LOGIN,
            server=SERVER,
            platform="mt5",
            password=PASSWORD,
            request_key="fixture-request",
        )
    assert failed.value.code == "broker_provisioning_unavailable"
    assert [request["method"] for request in transport.requests].count("POST") == 1

    # MetaApi's long-running answer (202) is waited for inside the one create call.
    transport = Scripted(
        httpx.Response(200, json=[]),
        httpx.Response(200, json=[]),
        httpx.Response(202, headers={"retry-after": "0.01"}, json={"message": "validating"}),
        httpx.Response(201, json={"id": "fixture-created", "state": "DEPLOYING"}),
        created("fixture-created"),
    )
    scripted(provisioning, transport)
    account, was_created = await provisioning.find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="fixture-request"
    )
    assert was_created and account.account_id == "fixture-created"
    posts = [request for request in transport.requests if request["method"] == "POST"]
    assert len(posts) == 2 and posts[0]["headers"] == posts[1]["headers"]
    assert json.dumps(posts[0]["body"]) == json.dumps(posts[1]["body"])
    # Account-entity calls only: no terminal socket was ever opened (R1).
    websocket = provisioning.api._metaapi_websocket_client
    assert not any(websocket._socket_instances.values())
    await provisioning.close()
    await trading.close()


@pytest.mark.asyncio
async def test_an_account_access_token_cannot_provision() -> None:
    provisioning = MetaApiProvisioning("fixture-account-token")
    transport = Scripted()
    scripted(provisioning, transport)
    with pytest.raises(LonoraError) as refused:
        await provisioning.accounts()
    assert refused.value.code == "broker_token_rejected" and transport.requests == []
    await provisioning.close()


@pytest.mark.asyncio
async def test_a_create_sent_again_carries_the_same_transaction_id() -> None:
    api = FakeProvisioningApi(lose_create_answer="before_commit")
    with pytest.raises(LonoraError):
        await client(api).find_or_create(
            login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="card-1"
        )
    account, created = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="card-1"
    )
    assert created and len(api.transactions) == 2 and len(set(api.transactions)) == 1
    assert len(api.transactions[0]) == 32 and api.transactions[0].isalpha()
    # The answer is lost after MetaApi stored the account: the same key finds it, and a
    # create sent again would carry the same transaction id.
    api.lose_create_answer = "after_commit"
    again, created_again = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="card-1"
    )
    assert not created_again and again.account_id == account.account_id
    assert len(api.accounts) == 1


@pytest.mark.asyncio
async def test_a_failed_read_after_a_successful_create_is_not_a_refusal() -> None:
    api = FakeProvisioningApi(lose_read_after_create=True)
    account, created = await client(api).find_or_create(
        login=LOGIN, server=SERVER, platform="mt5", password=PASSWORD, request_key="card-3"
    )
    assert created and account.login == LOGIN and len(api.accounts) == 1
