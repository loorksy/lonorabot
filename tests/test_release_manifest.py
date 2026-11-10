import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/release_manifest.py"
_spec = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
assert _spec and _spec.loader
release_manifest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_manifest)
ROOT = release_manifest.ROOT
build_manifest = release_manifest.build_manifest

VERSIONS = ROOT / "packages/db/migrations/versions"


def test_manifest_names_the_single_migration_head_on_disk() -> None:
    manifest = build_manifest(ROOT, None, "abc123", "2026-11-10T00:00:00Z")
    revisions = {path.stem for path in VERSIONS.glob("*.py")}
    assert manifest["migration_head"] in revisions
    # No other revision file names the head (as its parent or otherwise).
    head = str(manifest["migration_head"])
    others = [path for path in VERSIONS.glob("*.py") if path.stem != head]
    assert not any(f'"{head}"' in p.read_text() or f"'{head}'" in p.read_text() for p in others)
    assert manifest["schema"] == 1
    assert manifest["git_sha"] == "abc123"
    assert (
        manifest["min_client_version"]
        == json.loads((ROOT / "infra/release/compatibility.json").read_text())["min_client_version"]
    )


def test_explicit_version_wins_over_package_version() -> None:
    manifest = build_manifest(ROOT, "v9.9.9", "sha", "now")
    assert manifest["version"] == "v9.9.9"
    assert manifest["package_version"] != "v9.9.9"


def test_command_prints_json() -> None:
    output = subprocess.run(
        [sys.executable, str(SCRIPT), "--git-sha", "x"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert json.loads(output)["git_sha"] == "x"
