"""Public native app/domain bindings; never infer trust from client input."""

from typing import Any

from webauthn.helpers import bytes_to_base64url

from .env import Settings


def native_origins(settings: Settings) -> list[str]:
    return [
        "android:apk-key-hash:" + bytes_to_base64url(bytes.fromhex(value.replace(":", "")))
        for value in settings.passkey_android_fingerprints
    ]


def asset_links(settings: Settings) -> list[dict[str, Any]]:
    if not settings.passkey_android_fingerprints:
        return []
    return [
        {
            "relation": [
                "delegate_permission/common.handle_all_urls",
                "delegate_permission/common.get_login_creds",
            ],
            "target": {
                "namespace": "android_app",
                "package_name": settings.passkey_android_package,
                "sha256_cert_fingerprints": settings.passkey_android_fingerprints,
            },
        }
    ]
