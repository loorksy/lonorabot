#!/usr/bin/env python3
"""Build a universal signed release APK with the saved release identity."""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

mobile = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "lonora_android_signing", mobile / "scripts" / "android-signing.py"
)
assert spec and spec.loader
signing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signing)

if not (os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")):
    raise SystemExit(
        "Set ANDROID_HOME to an installed Android SDK (API 36, build-tools 36.0.0, NDK 27.1.12297006 and CMake 3.22.1)."
    )
javac = (
    Path(os.environ["JAVA_HOME"]) / "bin" / "javac"
    if os.environ.get("JAVA_HOME")
    else shutil.which("javac")
)
if not javac or not Path(javac).is_file():
    raise SystemExit(
        "A full Java 17+ JDK with javac is required; a Java runtime/JRE alone cannot compile Android."
    )
variables = [
    "LONORA_ANDROID_KEYSTORE",
    "LONORA_ANDROID_STORE_PASSWORD",
    "LONORA_ANDROID_KEY_ALIAS",
    "LONORA_ANDROID_KEY_PASSWORD",
]
if all(os.environ.get(variable) for variable in variables):
    credentials = {
        "keystore": os.environ[variables[0]],
        "store_password": os.environ[variables[1]],
        "alias": os.environ[variables[2]],
        "key_password": os.environ[variables[3]],
    }
elif any(os.environ.get(variable) for variable in variables):
    raise SystemExit(
        "Incomplete external release credentials; supply all four LONORA_ANDROID signing variables."
    )
else:
    credentials = signing.load_or_create()
env = os.environ.copy()
env.update(
    {
        "LONORA_ANDROID_KEYSTORE": credentials["keystore"],
        "LONORA_ANDROID_STORE_PASSWORD": credentials["store_password"],
        "LONORA_ANDROID_KEY_ALIAS": credentials["alias"],
        "LONORA_ANDROID_KEY_PASSWORD": credentials["key_password"],
        "NODE_ENV": "production",
    }
)
subprocess.run(
    ["pnpm", "exec", "expo", "prebuild", "--platform", "android", "--no-install"],
    cwd=mobile,
    env=env,
    check=True,
)
subprocess.run(
    [
        str(mobile / "android" / "gradlew"),
        ":app:assembleRelease",
        "--no-daemon",
        "--max-workers=4",
        "-PreactNativeArchitectures=armeabi-v7a,arm64-v8a,x86,x86_64",
    ],
    cwd=mobile / "android",
    env=env,
    check=True,
)
source = mobile / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
destination = mobile.parents[1] / ".runtime" / "releases" / "android" / "lonora.apk"
destination.parent.mkdir(parents=True, exist_ok=True)
candidate = destination.with_name("lonora.candidate.apk")
shutil.copy2(source, candidate)
subprocess.run(
    [sys.executable, str(mobile / "scripts" / "android-verify.py"), str(candidate)],
    cwd=mobile,
    env=env,
    check=True,
)
os.replace(candidate, destination)
os.replace(candidate.with_suffix(".json"), destination.with_suffix(".json"))
# These verified artifacts are public downloads, unlike the private signing directory.
destination.parent.chmod(0o755)
destination.chmod(0o644)
destination.with_suffix(".json").chmod(0o644)
print(f"Signed universal release APK: {destination}")
