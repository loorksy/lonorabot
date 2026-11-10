"""Write the release manifest baked into the server image as /app/release.json.

The manifest tells `lonora update` what it is about to install: the version, the
source commit, the single Alembic migration head and the oldest mobile/web client
version this server still serves. It reads migration files only; no database.
"""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parent.parent
VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def migration_head(root: Path = ROOT) -> str:
    script = ScriptDirectory.from_config(Config(str(root / "packages/db/alembic.ini")))
    heads = script.get_heads()
    if len(heads) != 1:
        raise SystemExit(f"Expected one migration head, found {sorted(heads)}")
    return heads[0]


def build_manifest(
    root: Path, version: str | None, git_sha: str, built_at: str
) -> dict[str, object]:
    package_version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    compatibility = json.loads((root / "infra/release/compatibility.json").read_text())
    minimum = compatibility["min_client_version"]
    if not isinstance(minimum, str) or not VERSION.match(minimum):
        raise SystemExit("min_client_version must be MAJOR.MINOR.PATCH")
    return {
        "schema": 1,
        "version": version or package_version,
        "package_version": package_version,
        "git_sha": git_sha,
        "built_at": built_at,
        "migration_head": migration_head(root),
        "min_client_version": minimum,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="")
    parser.add_argument("--git-sha", default="unknown")
    parser.add_argument("--built-at", default="unknown")
    arguments = parser.parse_args()
    manifest = build_manifest(
        ROOT, arguments.version or None, arguments.git_sha, arguments.built_at
    )
    json.dump(manifest, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
