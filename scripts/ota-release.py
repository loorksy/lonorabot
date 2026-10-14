"""Offline signed Expo Updates publisher. Never uploads credentials or exports private keys."""

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".config/lonora/ota/private.pem"
CERT = ROOT / "apps/mobile/certificates/ota.pem"


def atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def initialize() -> None:
    if KEY.exists() or CERT.exists():
        if not KEY.exists() or not CERT.exists():
            raise ValueError(
                "Existing signing identity incomplete; restore its key/certificate, never rotate silently"
            )
        signing_key(KEY, CERT)
        return
    KEY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(KEY.parent, 0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Lonora OTA")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
        .sign(key, hashes.SHA256())
    )
    descriptor = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    atomic(CERT, cert.public_bytes(serialization.Encoding.PEM))


def signing_key(path: Path, certificate: Path) -> rsa.RSAPrivateKey:
    if path.stat().st_mode & 0o077:
        raise ValueError("Signing key must have mode 600")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    public = x509.load_pem_x509_certificate(certificate.read_bytes()).public_key()
    if not isinstance(key, rsa.RSAPrivateKey) or not isinstance(public, rsa.RSAPublicKey):
        raise ValueError("RSA signing identity required")
    if key.public_key().public_numbers() != public.public_numbers():
        raise ValueError("Signing key does not match pinned mobile certificate")
    return key


def encoded(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def publish(
    export: Path,
    destination: Path,
    platform: str,
    runtime: str,
    channel: str,
    base_url: str,
    key: rsa.RSAPrivateKey,
    rollback: bool = False,
) -> str:
    if not re.fullmatch(r"[a-fA-F0-9]{40,64}", runtime):
        raise ValueError("Use the native fingerprint runtime, not the application version")
    if platform not in {"android", "ios"} or channel not in {"preview", "production"}:
        raise ValueError("Invalid publication target")
    if not re.fullmatch(r"https://[^/?#]+(?:/[^?#]*)?", base_url):
        raise ValueError("Public HTTPS update URL required")
    release = str(uuid4())
    target = destination / "releases" / channel / platform / runtime
    folder = target / release
    created = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if rollback:
        payload = encoded({"type": "rollBackToEmbedded", "parameters": {"commitTime": created}})
        stem = "directive"
    else:
        metadata = json.loads((export / "metadata.json").read_text())
        if metadata.get("version") != 0 or metadata.get("bundler") != "metro":
            raise ValueError("Unsupported Expo export metadata")
        files = metadata["fileMetadata"][platform]

        def asset(relative: str, extension: str) -> dict[str, str]:
            source = (export / relative).resolve()
            if not source.is_relative_to(export.resolve()) or not source.is_file():
                raise ValueError("Export asset escapes bundle directory")
            if not re.fullmatch(r"[a-zA-Z0-9]{1,12}", extension):
                raise ValueError("Invalid asset extension")
            data = source.read_bytes()
            digest = hashlib.sha256(data).digest()
            filename = f"{digest.hex()}.{extension}"
            atomic(destination / "assets" / filename, data)
            return {
                "key": hashlib.md5(data, usedforsecurity=False).hexdigest(),
                "hash": base64.urlsafe_b64encode(digest).decode().rstrip("="),
                "fileExtension": "." + extension,
                "contentType": "application/javascript"
                if extension == "bundle"
                else (mimetypes.guess_type("file." + extension)[0] or "application/octet-stream"),
                "url": base_url.rstrip("/") + "/assets/" + filename,
            }

        public_config = export / "expo-public.json"
        extra = (
            {"expoClient": json.loads(public_config.read_text())} if public_config.is_file() else {}
        )
        payload = encoded(
            {
                "id": release,
                "createdAt": created,
                "runtimeVersion": runtime,
                "launchAsset": asset(files["bundle"], "bundle"),
                "assets": [asset(item["path"], item["ext"]) for item in files["assets"]],
                "metadata": {},
                "extra": extra,
            }
        )
        stem = "manifest"
    signature = base64.b64encode(key.sign(payload, padding.PKCS1v15(), hashes.SHA256()))
    atomic(folder / f"{stem}.json", payload)
    atomic(folder / f"{stem}.sig", signature)
    previous = None
    pointer = target / "active.json"
    if pointer.exists():
        previous = json.loads(pointer.read_bytes()).get("release_id")
    # Publish the pointer last, after every immutable asset, exact manifest and signature.
    atomic(
        pointer,
        encoded(
            {
                "release_id": release,
                "previous_release_id": previous,
                "rollout_percentage": 100,
                "rollback_to_embedded": rollback,
            }
        ),
    )
    return release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "publish", "rollback"])
    parser.add_argument("--export", type=Path)
    parser.add_argument("--destination", type=Path, default=ROOT / ".runtime/releases/ota")
    parser.add_argument("--platform", choices=["android", "ios"], default="android")
    parser.add_argument("--channel", choices=["preview", "production"], default="production")
    parser.add_argument("--runtime")
    parser.add_argument("--url", default="https://lonora.lork.cloud/api/mobile/updates")
    args = parser.parse_args()
    if args.command == "init":
        initialize()
        print("OTA signing identity ready; only the public certificate belongs in Git")
        return
    if not args.runtime or (args.command == "publish" and not args.export):
        parser.error("--runtime and --export (for publish) are required")
    print(
        publish(
            args.export or Path("."),
            args.destination,
            args.platform,
            args.runtime,
            args.channel,
            args.url,
            signing_key(KEY, CERT),
            args.command == "rollback",
        )
    )


if __name__ == "__main__":
    main()
