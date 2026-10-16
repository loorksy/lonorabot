#!/usr/bin/env python3
"""Verify the delivered APK, report device compatibility and diagnose existing installs."""

import argparse
import hashlib
import json
import os
import re
import shlex
import struct
import subprocess
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("apk", type=Path)
parser.add_argument(
    "--require-minimal-permissions",
    action="store_true",
    help="Reject camera, overlay and broad storage declarations in new releases.",
)
parser.add_argument(
    "--require-call-permissions",
    action="store_true",
    help="Reject missing native microphone/audio/wake-lock declarations in new releases.",
)
parser.add_argument(
    "--device", help="Optional adb serial; inspect an existing install without uninstalling it."
)
args = parser.parse_args()
apk = args.apk.resolve()
if not zipfile.is_zipfile(apk):
    raise SystemExit(
        "The file is not an APK/ZIP. HTML downloads often indicate a wrong URL or SPA fallback."
    )
sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "")
tools = sdk / "build-tools" / "36.0.0"


def run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)


verification = run([str(tools / "apksigner"), "verify", "--verbose", "--print-certs", str(apk)])
if re.search(r"CN\s*=\s*Android\s+Debug", verification, re.I):
    raise SystemExit("Debug signing certificate rejected for a release artifact.")
if "Verified using v2 scheme (APK Signature Scheme v2): true" not in verification:
    raise SystemExit("APK Signature Scheme v2 verification failed.")
subprocess.run([str(tools / "zipalign"), "-c", "-P", "16", "4", str(apk)], check=True)
badging = run([str(tools / "aapt"), "dump", "badging", str(apk)])
package = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
assert package, "Android package metadata missing"
package_id = package[1]
min_sdk = re.search(r"sdkVersion:'(\d+)'", badging)
target_sdk = re.search(r"targetSdkVersion:'(\d+)'", badging)
assert min_sdk and target_sdk, "Android SDK metadata missing"
if package_id != "ai.lonora.mobile":
    raise SystemExit("Unexpected Android application ID.")
if "application-debuggable" in badging:
    raise SystemExit("The APK is debuggable; release build rejected.")
if args.require_minimal_permissions or args.require_call_permissions:
    permissions = run([str(tools / "aapt"), "dump", "permissions", str(apk)])
    declared = set(re.findall(r"uses-permission: name='([^']+)'", permissions))
    missing = {
        f"android.permission.{name}"
        for name in ("RECORD_AUDIO", "MODIFY_AUDIO_SETTINGS", "WAKE_LOCK")
    } - declared
    if args.require_call_permissions and missing:
        raise SystemExit("Required native call permissions missing: " + ", ".join(sorted(missing)))
    forbidden = declared.intersection(
        f"android.permission.{name}"
        for name in (
            "CAMERA",
            "SYSTEM_ALERT_WINDOW",
            "READ_EXTERNAL_STORAGE",
            "WRITE_EXTERNAL_STORAGE",
        )
    )
    if args.require_minimal_permissions and forbidden:
        raise SystemExit(
            "Unnecessary release permissions declared: " + ", ".join(sorted(forbidden))
        )
with zipfile.ZipFile(apk) as archive:
    entries = archive.namelist()
    if "AndroidManifest.xml" not in entries or "classes.dex" not in entries:
        raise SystemExit("Android manifest or compiled classes missing.")
    if not any(name.endswith("index.android.bundle") for name in entries):
        raise SystemExit("Embedded JavaScript missing; a release must run without Metro.")
    abis = sorted(
        {name.split("/")[1] for name in entries if name.startswith("lib/") and name.endswith(".so")}
    )
    for name in entries:
        if not (name.startswith(("lib/arm64-v8a/", "lib/x86_64/")) and name.endswith(".so")):
            continue
        data = archive.read(name)
        if data[:4] != b"\x7fELF" or data[4] != 2:
            raise SystemExit(f"Invalid 64-bit native library: {name}")
        endian = "<" if data[5] == 1 else ">"
        offset = struct.unpack_from(endian + "Q", data, 32)[0]
        size, count = struct.unpack_from(endian + "HH", data, 54)
        for index in range(count):
            header = offset + index * size
            if (
                struct.unpack_from(endian + "I", data, header)[0] == 1
                and struct.unpack_from(endian + "Q", data, header + 48)[0] < 16384
            ):
                raise SystemExit(f"Native library does not support 16 KB pages: {name}")
if abis != ["arm64-v8a", "armeabi-v7a", "x86", "x86_64"]:
    raise SystemExit(f"Universal APK ABIs missing: {abis}")
certificate = re.search(r"Signer #1 certificate SHA-256 digest: (.+)", verification)
assert certificate, "APK signing certificate metadata missing"
expected_signer = os.environ.get("LONORA_EXPECTED_SIGNER_SHA256")
if expected_signer and (
    not certificate or certificate[1].lower() != expected_signer.lower().replace(":", "")
):
    raise SystemExit(
        "Signing certificate does not match the required production identity; refuse to publish this APK as an update."
    )
report = {
    "package": package_id,
    "version_code": int(package[2]),
    "version_name": package[3],
    "min_sdk": int(min_sdk[1]),
    "target_sdk": int(target_sdk[1]),
    "abis": abis,
    "sha256": hashlib.file_digest(apk.open("rb"), "sha256").hexdigest(),
    "bytes": apk.stat().st_size,
    "signer_sha256": certificate[1] if certificate else None,
    "debuggable": False,
    "signature_v2_verified": True,
    "zipalign_16kb_verified": True,
    "elf_16kb_verified": True,
}
apk.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
if args.device:
    adb = sdk / "platform-tools" / "adb"
    device_sdk = int(
        run([str(adb), "-s", args.device, "shell", "getprop", "ro.build.version.sdk"]).strip()
    )
    device_abis = (
        run([str(adb), "-s", args.device, "shell", "getprop", "ro.product.cpu.abilist"])
        .strip()
        .split(",")
    )
    issues: list[str] = []
    if device_sdk < int(min_sdk[1]):
        issues.append(f"Device API{device_sdk} is below the required API{min_sdk[1]}.")
    if not set(device_abis).intersection(abis):
        issues.append(f"Device ABIs {device_abis} are unsupported by this APK.")
    installed = run([str(adb), "-s", args.device, "shell", "pm", "path", package_id]).strip()
    if installed.startswith("package:"):
        destination = apk.parent / "installed-base.apk"
        copied = subprocess.run(
            [
                str(adb),
                "-s",
                args.device,
                "pull",
                installed.splitlines()[0].removeprefix("package:"),
                str(destination),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if copied.returncode:
            # Old Android adb file-stat protocols can reject an existing readable APK.
            with destination.open("wb") as stream:
                subprocess.run(
                    [
                        str(adb),
                        "-s",
                        args.device,
                        "exec-out",
                        "cat " + shlex.quote(installed.splitlines()[0].removeprefix("package:")),
                    ],
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    check=True,
                    timeout=30,
                )
        original = run([str(tools / "apksigner"), "verify", "--print-certs", str(destination)])
        old_certificate = re.search(r"Signer #1 certificate SHA-256 digest: (.+)", original)
        old_badging = run([str(tools / "aapt"), "dump", "badging", str(destination)])
        old_code = re.search(r"versionCode='(\d+)'", old_badging)
        if old_code and int(old_code[1]) > int(package[2]):
            issues.append(
                f"Version downgrade: installed code{old_code[1]} exceeds new code{package[2]}."
            )
        if not old_certificate or old_certificate[1] != certificate[1]:
            issues.append(
                "Signing identity differs from the installed app. Restore its original release key before building an update."
            )
        print(
            "Existing install signing identity:",
            "MATCH"
            if old_certificate and old_certificate[1] == report["signer_sha256"]
            else "DIFFERENT: this APK cannot update it. Restore the original signing key or use a separately approved migration; uninstalling deletes app-local state.",
        )
    else:
        print("No previous Lonora installation on the selected device.")
    if issues:
        raise SystemExit("Update incompatible: " + " ".join(issues))
