import pytest
from lonora_api.device_metadata import asset_links, native_origins
from lonora_api.env import Settings
from lonora_auth.devices import relying_party
from lonora_core.user_error import LonoraError


def test_native_trust_is_unconfigured_until_public_release_certificate_is_supplied():
    settings = Settings.model_validate(
        {
            "database_url": "sqlite+aiosqlite://",
            "encryption_key": "fixture-only",
            "bootstrap_token": "fixture-only-authorization-test",
            "passkey_android_fingerprints": [],
        }
    )
    assert asset_links(settings) == [] and native_origins(settings) == []
    settings = Settings.model_validate(
        {**settings.model_dump(), "passkey_android_fingerprints": [":".join(["aa"] * 32)]}
    )
    target = asset_links(settings)[0]["target"]
    assert target["package_name"] == "ai.lonora.mobile"
    assert target["sha256_cert_fingerprints"] == [":".join(["AA"] * 32)]
    assert native_origins(settings) == ["android:apk-key-hash:" + "q" * 42 + "o"]


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "https://user@example.com",
        "https://example.com/path",
        "https://example.com?x=1",
        "file:///tmp",
    ],
)
def test_device_rp_does_not_accept_insecure_or_ambiguous_origins(origin: str):
    with pytest.raises(LonoraError, match="device_secure_origin_required"):
        relying_party(origin)


def test_https_rp_preserves_hostname_and_local_development_is_explicit():
    assert relying_party("https://lonora.example:8443") == "lonora.example"
    assert relying_party("http://localhost:8000") == "localhost"
