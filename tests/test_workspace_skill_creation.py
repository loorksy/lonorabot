"""Local package provenance and bounds use existing source/validation contracts."""

import hashlib
from typing import Any

import pytest
from lonora_agent.skills.packages import (
    PackageVersion,
    prepare_workspace_package,
    validation_image,
)
from lonora_agent.workspace import encode_snapshot
from lonora_core.user_error import LonoraError
from lonora_tools.skills import SkillAdaptationReview, SkillPackageCreateInput
from pydantic import ValidationError

DOCUMENT = "---\nname: local-statistics\ndescription: Inspect exact broker observations before estimating historical dispersion.\n---\nUse verified observations. This procedure cannot authorize financial execution.\n"
SOURCE = "import statistics\nprint(statistics.mean([1, 2, 3]))\n"
IMAGE = "sha256:" + "a" * 64
REVIEW = SkillAdaptationReview(
    source_behavior="Calculate descriptive statistics on a bounded supplied historical sample.",
    adapted_behavior="Calculate the same statistics on exact-symbol owner-scoped historical observations.",
    assumptions=["The caller checks symbol identity and timestamps before supplying observations."],
    limitations=["A smoke test is neither a strategy validation nor a maximum-loss guarantee."],
)


def prepare(files: dict[str, bytes] | None = None, **changes: Any):
    arguments: dict[str, Any] = {
        "agent_id": "owner-agent",
        "run_id": "origin-run",
        "workspace_revision": 7,
        "source_directory": "draft",
        "version": "1.0.0",
        "adapted_content": DOCUMENT,
        "review": REVIEW,
        **changes,
    }
    return prepare_workspace_package(
        files
        if files is not None
        else {"draft/SKILL.md": DOCUMENT.encode(), "draft/stats.py": SOURCE.encode()},
        **arguments,
    )


def test_workspace_origin_is_real_and_installed_copy_is_exact():
    entry, files = prepare()
    assert entry.source_kind == "workspace"
    assert entry.repository_url is entry.commit is entry.archive_sha256 is None
    assert entry.workspace_source is not None
    assert entry.workspace_source.agent_id == "owner-agent"
    assert entry.workspace_source.run_id == "origin-run"
    assert entry.workspace_source.workspace_revision == 7
    assert (
        entry.workspace_source.snapshot_sha256
        == hashlib.sha256(
            encode_snapshot(
                {"draft/SKILL.md": DOCUMENT.encode(), "draft/stats.py": SOURCE.encode()}
            )
        ).hexdigest()
    )
    assert entry.payload.manifest is not None and entry.payload.manifest.source == "installed"
    assert not entry.payload.enabled and entry.payload.manifest.activation.mode == "explicit"
    assert files["skills/local-statistics/1.0.0/stats.py"] == SOURCE
    assert entry.source_sha256 == hashlib.sha256(DOCUMENT.encode()).hexdigest()
    assert entry.files == {
        name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()
    }
    assert entry.external_imports == {"skills/local-statistics/1.0.0/stats.py": []}
    assert entry.payload.manifest.required_capabilities == []


def test_unrelated_source_is_not_copied_or_hashed():
    entry, files = prepare({"draft/SKILL.md": DOCUMENT.encode(), "other/private.txt": b"unrelated"})
    assert len(files) == 1 and "unrelated" not in str(files)
    assert entry.workspace_source is not None
    assert (
        entry.workspace_source.snapshot_sha256
        == hashlib.sha256(encode_snapshot({"draft/SKILL.md": DOCUMENT.encode()})).hexdigest()
    )
    assert not entry.utilities
    assert validation_image(entry) is None


@pytest.mark.parametrize(
    "directory",
    [
        "../draft",
        "/draft",
        "draft/../other",
        "draft//nested",
        "draft/.",
        "draft\\nested",
        "draft\x00bad",
    ],
)
def test_source_directory_uses_existing_lexical_boundary(directory: str):
    with pytest.raises(LonoraError, match="workspace_path_unsafe"):
        prepare(source_directory=directory)


def test_source_document_required_and_frontmatter_identity_cannot_change():
    with pytest.raises(LonoraError, match="skill_package_document_missing"):
        prepare({"draft/readme.txt": b"not a Skill"})
    with pytest.raises(LonoraError, match="skill_frontmatter_invalid"):
        prepare(adapted_content=DOCUMENT.replace("name: local-statistics", "name: forged"))
    with pytest.raises(LonoraError, match="skill_frontmatter_invalid"):
        prepare({"draft/SKILL.md": b"not frontmatter"})


@pytest.mark.parametrize(
    "body", [b"\x00binary", b"\xff\xfe", b"\x7fELF printable", b"printable\x01control"]
)
def test_binary_data_cannot_hide_as_utf8_text(body: bytes):
    with pytest.raises(LonoraError, match="skill_package_binary_unsupported"):
        prepare({"draft/SKILL.md": DOCUMENT.encode(), "draft/helper.py": body})


def test_nested_packages_are_not_implicitly_installed():
    with pytest.raises(LonoraError, match="skill_package_nested_unsupported"):
        prepare({"draft/SKILL.md": DOCUMENT.encode(), "draft/nested/SKILL.md": DOCUMENT.encode()})


@pytest.mark.parametrize("limit", ["files", "file", "total"])
def test_package_bounds_are_independent_of_larger_workspace_bounds(limit: str):
    files = {"draft/SKILL.md": DOCUMENT.encode()}
    if limit == "files":
        files.update({f"draft/file-{index}.txt": b"x" for index in range(64)})
    elif limit == "file":
        files["draft/large.txt"] = b"x" * 262145
    else:
        files.update({f"draft/file-{index}.txt": b"x" * 262144 for index in range(4)})
    with pytest.raises(LonoraError, match="skill_package_(?:too_large|file_too_large)"):
        prepare(files)


def test_provenance_discriminant_preserves_legacy_git_and_rejects_fiction():
    local, _ = prepare()
    payload = local.model_dump(mode="json")
    with pytest.raises(ValidationError):
        PackageVersion.model_validate({**payload, "commit": "a" * 40})
    with pytest.raises(ValidationError):
        PackageVersion.model_validate({**payload, "workspace_source": None})
    with pytest.raises(ValidationError):
        PackageVersion.model_validate(
            {**payload, "source_kind": "github", "workspace_source": None}
        )
    github = {
        key: value
        for key, value in payload.items()
        if key not in {"source_kind", "workspace_source"}
    }
    github.update(
        repository_url="https://github.com/example/research",
        commit="b" * 40,
        archive_sha256="c" * 64,
    )
    assert PackageVersion.model_validate(github).source_kind == "github"


def test_actual_source_hash_and_single_reviewed_image_are_required_for_smoke_receipts():
    entry, _ = prepare()
    path = entry.utilities[0]
    with pytest.raises(LonoraError, match="skill_package_validation_required"):
        validation_image(entry)
    entry.validation = {path: {"exit_code": 0, "source_sha256": entry.files[path], "image": IMAGE}}
    assert validation_image(entry) == IMAGE
    for field, value in [("exit_code", 1), ("source_sha256", "0" * 64), ("image", "python:latest")]:
        entry.validation[path] = {
            "exit_code": 0,
            "source_sha256": entry.files[path],
            "image": IMAGE,
            field: value,
        }
        with pytest.raises(LonoraError, match="skill_package_validation_required"):
            validation_image(entry)


def test_create_input_cannot_supply_agent_origin_authority_or_mutable_versions():
    valid = {
        "source_directory": "draft",
        "workspace_revision": 7,
        "version": "1.0.0",
        "expected_version": 0,
        "adapted_content": DOCUMENT,
        "review": REVIEW.model_dump(),
    }
    SkillPackageCreateInput.model_validate(valid)
    for field, value in [
        ("agent_id", "another-agent"),
        ("run_id", "fake-run"),
        ("enabled", True),
        ("allowed_tools", ["trade_execute"]),
        ("commit", "a" * 40),
    ]:
        with pytest.raises(ValidationError):
            SkillPackageCreateInput.model_validate({**valid, field: value})
    with pytest.raises(ValidationError):
        SkillPackageCreateInput.model_validate({**valid, "version": "latest"})
