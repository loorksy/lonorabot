#!/usr/bin/env python3
"""Install and cold-start a real release on a selected Android test device."""

import argparse
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("apk", type=Path)
parser.add_argument(
    "--serial", required=True, help="The explicit disposable emulator/test-device adb serial"
)
parser.add_argument("--output", type=Path, default=Path("/tmp/lonora-android-smoke"))
args = parser.parse_args()
sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or "")
adb = str(sdk / "platform-tools" / "adb")
args.output.mkdir(parents=True, exist_ok=True)
package = "ai.lonora.mobile"


def command(*values: str) -> str:
    return subprocess.check_output(
        [adb, "-s", args.serial, *values], text=True, stderr=subprocess.STDOUT
    )


def hierarchy() -> ET.Element:
    command("shell", "uiautomator", "dump", "/sdcard/lonora-ui.xml")
    return ET.fromstring(command("shell", "cat", "/sdcard/lonora-ui.xml"))


def labels(root: ET.Element) -> str:
    return " ".join(
        node.get("text", "") + " " + node.get("content-desc", "") for node in root.iter()
    )


def wait_screen() -> ET.Element:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            root = hierarchy()
            text = labels(root)
            if "Lonora" in text and ("تسجيل الدخول" in text or "Sign in" in text):
                return root
        except (ET.ParseError, subprocess.CalledProcessError):
            pass
        time.sleep(2)
    raise SystemExit("Release app did not reach the actual sign-in screen within 90 seconds.")


command("logcat", "-c")
print(command("install", "-r", str(args.apk.resolve())).strip())
command("shell", "am", "start", "-n", package + "/.MainActivity")
root = wait_screen()
print("PASS signed release installs and starts without Metro")
english = next(
    (
        node
        for node in root.iter()
        if node.get("content-desc") == "English" or node.get("text") == "English"
    ),
    None,
)
if english is not None:
    bounds = [int(value) for value in re.findall(r"\d+", english.get("bounds", ""))]
    if len(bounds) == 4:
        command(
            "shell",
            "input",
            "tap",
            str((bounds[0] + bounds[2]) // 2),
            str((bounds[1] + bounds[3]) // 2),
        )
        time.sleep(2)
        if "Sign in" not in labels(wait_screen()):
            raise SystemExit("Native language switch failed.")
        print("PASS native Arabic/English switch")
command("shell", "am", "force-stop", package)
command("shell", "am", "start", "-n", package + "/.MainActivity")
root = wait_screen()
if "Sign in" not in labels(root):
    raise SystemExit("SecureStore locale preference did not survive cold restart.")
print("PASS native preference survives cold restart")
print(command("install", "-r", str(args.apk.resolve())).strip())
command("shell", "am", "force-stop", package)
command("shell", "am", "start", "-n", package + "/.MainActivity")
root = wait_screen()
if "Sign in" not in labels(root):
    raise SystemExit("Signed update did not preserve native local preference.")
print("PASS same-key release update preserves app data")
command("shell", "screencap", "-p", "/sdcard/lonora-release.png")
command("pull", "/sdcard/lonora-release.png", str(args.output / "release.png"))
ET.ElementTree(root).write(args.output / "hierarchy.xml", encoding="utf-8")
logs = command("logcat", "-d", "-s", "AndroidRuntime:E", "ReactNativeJS:E")
(args.output / "errors.log").write_text(logs)
if "FATAL EXCEPTION" in logs or "JavascriptException" in logs:
    raise SystemExit("Android release crashed; see the captured native error log.")
print("PASS no native startup crash")
