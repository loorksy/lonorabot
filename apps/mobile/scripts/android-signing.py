#!/usr/bin/env python3
"""Create or reuse a private release identity outside the checkout; never print secrets."""

import json
import os
import secrets
import subprocess
from pathlib import Path


def signing_directory() -> Path:
    configured = os.environ.get("LONORA_SIGNING_DIR")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "lonora"
        / "android"
    )


def load_or_create() -> dict[str, str]:
    directory = signing_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    manifest = directory / "signing.json"
    keystore = directory / "lonora-release.p12"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        if not Path(data["keystore"]).is_file():
            raise SystemExit(
                "Signing manifest exists but its key is missing. Restore the backed-up key; do not generate a replacement identity."
            )
        return data
    if keystore.exists():
        raise SystemExit(
            "A release key already exists without its manifest. Restore credentials; refusing to overwrite it."
        )
    password = secrets.token_urlsafe(40)
    data = {
        "keystore": str(keystore),
        "alias": "lonora-release",
        "store_password": password,
        "key_password": password,
    }
    env = os.environ.copy()
    env["LONORA_PRIVATE_KEY_PASSWORD"] = password
    subprocess.run(
        [
            "keytool",
            "-genkeypair",
            "-noprompt",
            "-keystore",
            str(keystore),
            "-storetype",
            "PKCS12",
            "-storepass:env",
            "LONORA_PRIVATE_KEY_PASSWORD",
            "-keypass:env",
            "LONORA_PRIVATE_KEY_PASSWORD",
            "-alias",
            data["alias"],
            "-keyalg",
            "RSA",
            "-keysize",
            "3072",
            "-validity",
            "10000",
            "-dname",
            "CN=Lonora Release,O=Lonora",
        ],
        env=env,
        check=True,
    )
    keystore.chmod(0o600)
    descriptor = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(data, stream)
    return data


if __name__ == "__main__":
    data = load_or_create()
    print(
        f"Private release identity ready at {Path(data['keystore']).parent}. Back up the entire directory securely before moving build hosts."
    )
