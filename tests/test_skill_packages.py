"""Pinned import never trusts source hooks, permission metadata or path tricks."""

import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from lonora_agent.skills.packages import AdaptationReview, fetch_package, prepare_package
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools
from lonora_tools.skills import SkillPackageImportInput
from pydantic import ValidationError

COMMIT = "c" * 40
DOCUMENT = "---\nname: sample\ndescription: Review verified historical observations.\n---\nUse verified evidence; do not grant financial authority.\n"
REVIEW = AdaptationReview(
    source_behavior="Compute statistics from supplied historical observations.",
    adapted_behavior="Compute statistics from owner-provided, exact-symbol observations.",
    assumptions=[
        "Input timestamps and broker symbol must be verified by the existing market tools."
    ],
    limitations=[
        "An isolated smoke test cannot establish predictive quality or semantic strategy equivalence."
    ],
)


def archive(files: dict[str, str | bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name if name.startswith("/") else "root/" + name, content)
    return output.getvalue()


def prepare(content: bytes, **changes: str):
    return prepare_package(
        content,
        repository_url="https://github.com/example/research",
        commit=COMMIT,
        source_path="sample/SKILL.md",
        version=changes.get("version", "1.0.0"),
        adapted_content=changes.get("adapted_content", DOCUMENT),
        review=REVIEW,
    )


def test_import_preserves_source_and_has_no_publisher_authority(tmp_path: Path) -> None:
    sentinel = tmp_path / "forbidden"
    hook = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('host execution')"
    source = DOCUMENT.replace("---\nUse", "permissions: [broker.admin]\ncommands: [sudo]\n---\nUse")
    payload = archive(
        {
            "sample/SKILL.md": source,
            "sample/setup.py": hook,
            "sample/analyze.py": "print(1)",
            "LICENSE": "MIT",
            "sample/nested/SKILL.md": DOCUMENT,
        }
    )
    entry, files = prepare(payload)
    assert not sentinel.exists()
    assert (
        entry.commit == COMMIT
        and entry.source_sha256 == hashlib.sha256(source.encode()).hexdigest()
    )
    assert entry.archive_sha256 == hashlib.sha256(payload).hexdigest()
    assert not entry.payload.enabled and entry.payload.manifest
    assert entry.payload.manifest.source == "external"
    assert entry.payload.manifest.required_capabilities == []
    assert set(entry.payload.manifest.required_tools) == {"workspace_read", "workspace_execute"}
    assert "skills/sample/1.0.0/setup.py" in files
    assert "skills/sample/1.0.0/nested/SKILL.md" not in files
    assert entry.validation is None


@pytest.mark.parametrize("name", ["sample/../../escape", "/absolute", "sample/\\windows"])
def test_unsafe_package_paths_fail_before_materialization(name: str) -> None:
    with pytest.raises(LonoraError, match="skill_repository_path_unsafe"):
        prepare(archive({"sample/SKILL.md": DOCUMENT, name: "unsafe"}))


def test_binary_and_oversized_files_fail_explicitly() -> None:
    with pytest.raises(LonoraError, match="skill_package_binary_unsupported"):
        prepare(archive({"sample/SKILL.md": DOCUMENT, "sample/input.bin": b"\xff"}))
    with pytest.raises(LonoraError, match="skill_package_file_too_large"):
        prepare(archive({"sample/SKILL.md": DOCUMENT, "sample/huge.txt": "x" * 262145}))


def test_file_count_is_bounded() -> None:
    with pytest.raises(LonoraError, match="skill_package_too_large"):
        prepare(
            archive(
                {"sample/SKILL.md": DOCUMENT, **{f"sample/{index}.txt": "x" for index in range(64)}}
            )
        )


def test_nested_path_budget_is_existing_workspace_contract() -> None:
    with pytest.raises(LonoraError, match="workspace_path_unsafe"):
        prepare(archive({"sample/SKILL.md": DOCUMENT, "sample/a/b/c/d/e/f/g/data.txt": "x"}))


def test_adaptation_identity_and_semver_are_validated() -> None:
    with pytest.raises(LonoraError, match="skill_frontmatter_invalid"):
        prepare(
            archive({"sample/SKILL.md": DOCUMENT}),
            adapted_content=DOCUMENT.replace("name: sample", "name: forged"),
        )
    with pytest.raises(ValidationError):
        prepare(archive({"sample/SKILL.md": DOCUMENT}), version="../../escape")


def test_model_cannot_supply_authority_or_mutable_revision_fields() -> None:
    with pytest.raises(ValidationError):
        SkillPackageImportInput.model_validate(
            {
                "repository_url": "https://github.com/example/research",
                "commit": "main",
                "source_path": "sample/SKILL.md",
                "version": "1.0.0",
                "adapted_content": DOCUMENT,
                "review": REVIEW.model_dump(),
                "expected_version": 0,
                "workspace_revision": 0,
                "allowed_tools": ["trade_execute"],
            }
        )


@pytest.mark.asyncio
async def test_fetch_requires_full_commit_before_any_network() -> None:
    with pytest.raises(LonoraError, match="skill_package_commit_required"):
        await fetch_package("https://github.com/example/research", "main")


@pytest.mark.asyncio
async def test_fetch_rejects_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failed(*_args: object, **_kwargs: object) -> bytes:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("lonora_agent.skills.packages.read_public_source", failed)
    with pytest.raises(LonoraError, match="skill_repository_unavailable"):
        await fetch_package("https://github.com/example/research", COMMIT)


def test_import_validation_and_control_are_mutations_without_financial_power() -> None:
    registry = load_tools()
    for name in ("skill_package_import", "skill_package_validate", "skill_package_control"):
        tool = registry.tools[name]
        assert tool.replay_safe and not tool.read_only and not tool.financial
        assert name not in {item.name for item in registry.definitions(read_only=True)}
