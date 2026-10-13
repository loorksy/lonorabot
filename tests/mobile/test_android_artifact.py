"""Real release artifact guards for invalid downloads and wrong update identities."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "apps/mobile/scripts/android-verify.py"
APK = ROOT / ".runtime/releases/android/lonora.apk"
SDK = Path(os.environ.get("ANDROID_HOME") or ROOT / ".runtime/toolchains/android-sdk")
READY = APK.is_file() and (SDK / "build-tools/36.0.0/apksigner").is_file()


class AndroidArtifactChecks(unittest.TestCase):
    def verify(
        self, path: Path, expected_signer: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["ANDROID_HOME"] = str(SDK)
        if expected_signer:
            env["LONORA_EXPECTED_SIGNER_SHA256"] = expected_signer
        else:
            env.pop("LONORA_EXPECTED_SIGNER_SHA256", None)
        return subprocess.run(
            [sys.executable, str(VERIFY), str(path)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_html_download_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lonora.apk"
            path.write_text("<!doctype html><html>Lonora Web fallback</html>")
            response = self.verify(path)
            self.assertNotEqual(response.returncode, 0)
            self.assertIn("not an APK/ZIP", response.stderr)

    @unittest.skipUnless(READY, "Requires the real locally built APK and Android signing tools")
    def test_actual_release_verifies(self) -> None:
        response = self.verify(APK)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn('"signature_v2_verified": true', response.stdout)
        self.assertIn('"elf_16kb_verified": true', response.stdout)
        certificate = re.search(r'"signer_sha256": "([0-9a-f]{64})"', response.stdout)
        assert certificate
        self.assertEqual(self.verify(APK, certificate[1]).returncode, 0)

    @unittest.skipUnless(READY, "Requires the real locally built APK and Android signing tools")
    def test_wrong_update_certificate_is_rejected(self) -> None:
        # A known other certificate cannot satisfy this artifact's production guard.
        response = self.verify(APK, "0" * 64)
        self.assertNotEqual(response.returncode, 0)
        self.assertIn("does not match the required production identity", response.stderr)


if __name__ == "__main__":
    unittest.main()
