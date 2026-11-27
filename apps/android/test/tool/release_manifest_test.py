"""tool/release_manifest.py against a built APK (skipped without one or without ANDROID_HOME).

Run from apps/android: python3 -m unittest test/tool/release_manifest_test.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tool" / "release_manifest.py"
APK = Path(os.environ.get("LONORA_TEST_APK", ROOT / "build/app/outputs/flutter-apk/app-debug.apk"))


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(APK), *args], capture_output=True, text=True)


@unittest.skipUnless(APK.exists() and os.environ.get("ANDROID_HOME"), "needs a built APK and ANDROID_HOME")
class ReleaseManifestTest(unittest.TestCase):
    def test_metadata_is_unchanged(self) -> None:
        out = run()
        self.assertEqual(out.returncode, 0, out.stderr)
        info = json.loads(out.stdout)
        for key in ("file", "sha256", "size", "applicationId", "versionCode", "versionName", "minSdk", "targetSdk", "signerSha256", "signatureSchemes"):
            self.assertIn(key, info)

    def test_update_manifest(self) -> None:
        out = run("--update-manifest", "https://releases.example.com/lonora-android.apk", "--notes-ar", "إصلاحات.", "--notes-en", "Fixes.")
        self.assertEqual(out.returncode, 0, out.stderr)
        manifest = json.loads(out.stdout)
        meta = json.loads(run().stdout)
        self.assertEqual(
            manifest,
            {
                "package": meta["applicationId"],
                "version_name": meta["versionName"],
                "version_code": meta["versionCode"],
                "url": "https://releases.example.com/lonora-android.apk",
                "notes": {"ar": "إصلاحات.", "en": "Fixes."},
            },
        )

    def test_notes_are_optional(self) -> None:
        out = run("--update-manifest", "https://releases.example.com/l.apk")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("notes", json.loads(out.stdout))

    def test_refuses_links_the_app_would_ignore(self) -> None:
        for url in ("http://releases.example.com/l.apk", "https://user:pw@example.com/l.apk", "https://lonora.example.com/download/lonora.apk"):
            out = run("--update-manifest", url)
            self.assertNotEqual(out.returncode, 0, url)
            self.assertEqual(out.stdout, "", url)


if __name__ == "__main__":
    unittest.main()
