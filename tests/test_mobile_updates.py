"""Real signature/protocol tests; no broker, database, or signing secret is needed."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI
from lonora_api.errors import install_errors
from lonora_api.routes.mobile_updates import router

spec = importlib.util.spec_from_file_location(
    "ota_publisher", Path(__file__).parents[1] / "scripts/ota-release.py"
)
assert spec and spec.loader
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
RUNTIME = "a" * 40


Release = tuple[FastAPI, Path, Path, rsa.RSAPrivateKey, str]


@pytest.fixture
def release(tmp_path: Path) -> Release:
    export = tmp_path / "export"
    export.mkdir()
    (export / "main.js").write_bytes(b"real bundle fixture")
    (export / "image.png").write_bytes(b"image fixture")
    (export / "metadata.json").write_text(
        json.dumps(
            {
                "version": 0,
                "bundler": "metro",
                "fileMetadata": {
                    "android": {
                        "bundle": "main.js",
                        "assets": [{"path": "image.png", "ext": "png"}],
                    }
                },
            }
        )
    )
    (export / "expo-public.json").write_text(
        json.dumps(
            {"name": "Lonora", "slug": "lonora", "scheme": "lonora", "extra": {"router": {}}}
        )
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root = tmp_path / "releases"
    identity = publisher.publish(
        export,
        root,
        "android",
        RUNTIME,
        "production",
        "https://lonora.lork.cloud/api/mobile/updates",
        key,
    )
    app = FastAPI()
    app.state.runtime = SimpleNamespace(settings=SimpleNamespace(ota_root=root))
    app.include_router(router, prefix="/api")
    install_errors(app)
    return app, root, export, key, identity


def headers(**extra: str) -> dict[str, str]:
    return {
        "expo-protocol-version": "1",
        "expo-platform": "android",
        "expo-runtime-version": RUNTIME,
        "expo-channel-name": "production",
        **extra,
    }


@pytest.mark.asyncio
async def test_signed_manifest_assets_and_unchanged(release: Release) -> None:
    app, _, _, key, identity = release
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://lonora.lork.cloud"
    ) as client:
        response = await client.get("/api/mobile/updates", headers=headers())
        assert response.status_code == 200
        signature = response.headers["expo-signature"].split('"')[1]
        key.public_key().verify(
            base64.b64decode(signature), response.content, padding.PKCS1v15(), hashes.SHA256()
        )
        manifest = response.json()
        assert manifest["id"] == identity and manifest["runtimeVersion"] == RUNTIME
        assert manifest["extra"]["expoClient"]["scheme"] == "lonora"
        for asset in [manifest["launchAsset"], *manifest["assets"]]:
            data = (await client.get(asset["url"])).content
            assert asset["key"] == hashlib.md5(data, usedforsecurity=False).hexdigest()
            assert asset["hash"] == base64.urlsafe_b64encode(
                hashlib.sha256(data).digest()
            ).decode().rstrip("=")
        assert (
            await client.get(
                "/api/mobile/updates", headers=headers(**{"expo-current-update-id": identity})
            )
        ).status_code == 204
        assert (
            await client.get(
                "/api/mobile/updates", headers=headers(**{"expo-runtime-version": "b" * 40})
            )
        ).status_code == 204
        assert (
            await client.get("/api/mobile/updates", headers=headers(**{"expo-platform": "web"}))
        ).status_code == 400


@pytest.mark.asyncio
async def test_corruption_and_symlink_rejected(release: Release, tmp_path: Path) -> None:
    app, root, _, _, _ = release
    filename = next((root / "assets").iterdir())
    filename.write_bytes(b"tampered")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://lonora.lork.cloud"
    ) as client:
        assert (await client.get("/api/mobile/updates/assets/" + filename.name)).status_code == 503
        filename.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(b"secret fixture")
        filename.symlink_to(outside)
        assert (await client.get("/api/mobile/updates/assets/" + filename.name)).status_code == 503


@pytest.mark.asyncio
async def test_signed_rollback_directive(release: Release) -> None:
    app, root, export, key, _ = release
    publisher.publish(
        export,
        root,
        "android",
        RUNTIME,
        "production",
        "https://lonora.lork.cloud/api/mobile/updates",
        key,
        rollback=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://lonora.lork.cloud"
    ) as client:
        response = await client.get("/api/mobile/updates", headers=headers())
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("multipart/mixed")
        parts = response.content.split(b"\r\n\r\n", 1)
        signature = parts[0].decode().split('sig="')[1].split('"')[0]
        payload = parts[1].split(b"\r\n--lonora-ota-directive")[0]
        key.public_key().verify(
            base64.b64decode(signature), payload, padding.PKCS1v15(), hashes.SHA256()
        )
        assert json.loads(payload)["type"] == "rollBackToEmbedded"


def test_export_traversal_and_identity_pin(release: Release, tmp_path: Path) -> None:
    _, root, export, key, _ = release
    metadata = json.loads((export / "metadata.json").read_text())
    metadata["fileMetadata"]["android"]["bundle"] = "../outside"
    (export / "metadata.json").write_text(json.dumps(metadata))
    (tmp_path / "outside").write_bytes(b"outside")
    with pytest.raises(ValueError, match="escapes"):
        publisher.publish(
            export,
            root,
            "android",
            RUNTIME,
            "production",
            "https://lonora.lork.cloud/api/mobile/updates",
            key,
        )


def test_pinned_certificate_has_native_required_code_signing_usages() -> None:
    from cryptography import x509
    from cryptography.x509.oid import ExtendedKeyUsageOID

    certificate = x509.load_pem_x509_certificate(publisher.CERT.read_bytes())
    assert certificate.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature
    assert (
        ExtendedKeyUsageOID.CODE_SIGNING
        in certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    )


def test_signing_key_must_match_native_pin(tmp_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = tmp_path / "private.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private.chmod(0o600)
    with pytest.raises(ValueError, match="does not match"):
        publisher.signing_key(private, publisher.CERT)
    private.chmod(0o644)
    with pytest.raises(ValueError, match="mode 600"):
        publisher.signing_key(private, publisher.CERT)
