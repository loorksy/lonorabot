#!/usr/bin/env python3
"""Print public verification metadata for a built Lonora Android APK as JSON, or the in-app
update manifest of sideloaded builds for it.

Reads the package name and version from the APK with aapt2 (Android build-tools) and the
signing certificate digest with apksigner, plus the file's SHA-256. Nothing secret is read.

Usage:
  python3 tool/release_manifest.py APK
  python3 tool/release_manifest.py APK --update-manifest URL [--notes-ar TEXT] [--notes-en TEXT]

The second form prints {"package", "version_name", "version_code", "url", "notes": {"ar", "en"}}
as lib/platform/updates/update_manifest.dart reads it; URL is where the APK is downloaded from
(https only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _build_tool(name: str) -> str:
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not sdk:
        raise SystemExit("ANDROID_HOME is not set")
    versions = sorted((Path(sdk) / "build-tools").iterdir(), key=lambda p: [int(x) if x.isdigit() else 0 for x in re.split(r"[.-]", p.name)])
    return str(versions[-1] / name)


def _badging(apk: Path) -> tuple[str, re.Match[str]]:
    badging = subprocess.run([_build_tool("aapt2"), "dump", "badging", str(apk)], check=True, capture_output=True, text=True).stdout
    package = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", badging)
    if package is None:
        raise SystemExit("could not read the package from aapt2 badging")
    return badging, package


def update_manifest(apk: Path, url: str, notes: dict[str, str]) -> dict[str, object]:
    """The manifest the app accepts: an https link that is not the Expo companion's APK."""
    link = urlsplit(url)
    if link.scheme != "https" or not link.hostname or link.username or link.password:
        raise SystemExit("the update URL must be https, with a host and no credentials")
    if link.path.lower().endswith("/download/lonora.apk") or "ai.lonora.mobile" in link.path.lower():
        raise SystemExit("that link is the Expo companion app (ai.lonora.mobile), not this app")
    _, package = _badging(apk)
    manifest: dict[str, object] = {
        "package": package.group(1),
        "version_name": package.group(3),
        "version_code": int(package.group(2)),
        "url": url,
    }
    if notes:
        manifest["notes"] = notes
    return manifest


def main(apk_path: str) -> None:
    apk = Path(apk_path)
    badging, package = _badging(apk)
    min_sdk = re.search(r"minSdkVersion:'(\d+)'", badging)
    target_sdk = re.search(r"targetSdkVersion:'(\d+)'", badging)
    certs = subprocess.run(
        [_build_tool("apksigner"), "verify", "--print-certs", "--verbose", str(apk)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    digest = re.search(r"certificate SHA-256 digest: ([0-9a-f]+)", certs)
    schemes = sorted(set(re.findall(r"Verified using (v\d[^:]*) scheme[^:]*: true", certs)))
    info = {
        "file": apk.name,
        "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        "size": apk.stat().st_size,
        "applicationId": package.group(1),
        "versionCode": int(package.group(2)),
        "versionName": package.group(3),
        "minSdk": int(min_sdk.group(1)) if min_sdk else None,
        "targetSdk": int(target_sdk.group(1)) if target_sdk else None,
        "signerSha256": digest.group(1) if digest else None,
        "signatureSchemes": schemes,
    }
    json.dump(info, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(usage=__doc__)
    parser.add_argument("apk")
    parser.add_argument("--update-manifest", metavar="URL")
    parser.add_argument("--notes-ar", metavar="TEXT")
    parser.add_argument("--notes-en", metavar="TEXT")
    args = parser.parse_args()
    if args.update_manifest is None:
        main(args.apk)
    else:
        notes = {lang: text for lang, text in (("ar", args.notes_ar), ("en", args.notes_en)) if text}
        json.dump(update_manifest(Path(args.apk), args.update_manifest, notes), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
