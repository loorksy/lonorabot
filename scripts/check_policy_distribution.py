"""Build the production wheel offline and exercise its installed policy layout."""

import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from unittest.mock import patch
from zipfile import ZipFile

from lonora_agent.skills.loader import load_constitution, resources_root
from lonora_agent.skills.registry import built_in_skills
from lonora_agent.skills.system_policy import mandatory_policy, validate_system_policy
from lonora_agent.skills.visual_policy import native_visual_policy
from lonora_tools.loader import load_tools

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    expected = mandatory_policy()
    expected_visual = native_visual_policy()
    expected_design = built_in_skills()["lonora-design"]
    with tempfile.TemporaryDirectory(prefix="lonora_policy_distribution_") as temporary:
        target = Path(temporary)
        source = target / "source"
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]
        # Stage only declared source/resources. pip/setuptools may create build/
        # beside its input; keeping that outside the checkout avoids generated
        # duplicate packages polluting type checks or subsequent deployments.
        files = {ROOT / name for name in ("pyproject.toml", "LICENSE", "THIRD_PARTY_NOTICES.md")}
        directories = metadata["package-dir"]
        for directory in set(directories.values()):
            files.update((ROOT / directory).rglob("*.py"))
        for names in metadata["data-files"].values():
            for name in names:
                files.update(ROOT.glob(name))
        for package, patterns in metadata.get("package-data", {}).items():
            for pattern in patterns:
                files.update((ROOT / directories[package]).glob(pattern))
        for path in files:
            relative = path.resolve().relative_to(ROOT)
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(target),
                str(source),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if result.returncode:
            raise SystemExit("Production wheel build failed:\n" + result.stdout + result.stderr)
        wheels = list(target.glob("lonora-*.whl"))
        if len(wheels) != 1:
            raise SystemExit("Expected exactly one production wheel")
        with ZipFile(wheels[0]) as wheel:
            for name in wheel.namelist():
                marker = ".data/data/share/lonora/"
                if marker not in name or name.endswith("/"):
                    continue
                relative = PurePosixPath(name.split(marker, 1)[1])
                if relative.is_absolute() or ".." in relative.parts:
                    raise SystemExit("Unexpected distribution resource path")
                destination = target / "share/lonora" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(wheel.read(name))
        # Force the real loader's installed-layout fallback, without relying on
        # the repository's resource directory or changing the active environment.
        fake_module = target / "lib/python3.12/site-packages/lonora_agent/skills/loader.py"
        with (
            patch("lonora_agent.skills.loader.__file__", str(fake_module)),
            patch.object(sys, "prefix", str(target)),
        ):
            assert resources_root() == target / "share/lonora"
            assert mandatory_policy() == expected
            assert native_visual_policy() == expected_visual
            assert built_in_skills()["lonora-design"] == expected_design
            assert len(load_constitution()) == 7
            validate_system_policy(set(load_tools().tools))
    print(
        "Production wheel ships valid operating policy/manifest; installed fallback loads all mandatory rules"
    )


if __name__ == "__main__":
    main()
