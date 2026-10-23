"""Bounded pinned packages and adaptation records, never publisher authority."""

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any, Literal, cast

import httpx
import yaml
from lonora_contracts.domain import Contract
from lonora_contracts.skills import AgentSkill, SkillActivation, SkillManifest, SkillVersion
from lonora_core.agent_skill import validate_skill_name
from lonora_core.user_error import LonoraError
from lonora_tools.skills import SkillAdaptationReview as AdaptationReview
from pydantic import Field, TypeAdapter, model_validator

from .document import FRONTMATTER, skill_document
from .repository import (
    MAX_ARCHIVE_BYTES,
    archive_files,
    inspect_archive,
    inspect_utilities,
    read_public_source,
    repository_identity,
)


class WorkspaceSource(Contract):
    agent_id: str = Field(min_length=1, max_length=80)
    run_id: str = Field(min_length=1, max_length=80)
    workspace_revision: int = Field(ge=0)
    source_directory: str = Field(min_length=1, max_length=256)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PackageVersion(Contract):
    payload: AgentSkill
    source_kind: Literal["github", "workspace"] = "github"
    repository_url: str | None = None
    commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    archive_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    workspace_source: WorkspaceSource | None = None
    source_path: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_files: dict[str, str] = Field(default_factory=dict, max_length=32)
    files: dict[str, str] = Field(max_length=64)
    utilities: list[str] = Field(max_length=64)
    external_imports: dict[str, list[str]] = Field(default_factory=dict, max_length=64)
    unmaterialized_dependencies: list[str] = Field(default_factory=list, max_length=64)
    review: AdaptationReview
    validation: dict[str, Any] | None = None

    @model_validator(mode="after")
    def truthful_provenance(self) -> "PackageVersion":
        if self.source_kind == "github":
            if (
                not self.repository_url
                or not self.commit
                or not self.archive_sha256
                or self.workspace_source
            ):
                raise ValueError("skill_package_github_provenance_required")
            repository_identity(self.repository_url)
        elif self.workspace_source is None or any(
            value is not None for value in (self.repository_url, self.commit, self.archive_sha256)
        ):
            raise ValueError("skill_package_workspace_provenance_required")
        return self


def validation_image(entry: PackageVersion) -> str | None:
    """Successful immutable utility receipts must describe one execution image."""
    if not entry.utilities:
        return None
    images: set[str] = set()
    for path in entry.utilities:
        raw = (entry.validation or {}).get(path)
        if not isinstance(raw, dict):
            raise LonoraError("skill_package_validation_required", 409)
        receipt = cast(dict[str, Any], raw)
        if (
            receipt.get("exit_code") != 0
            or receipt.get("source_sha256") != entry.files.get(path)
            or not isinstance(receipt.get("image"), str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", receipt["image"])
        ):
            raise LonoraError("skill_package_validation_required", 409)
        images.add(receipt["image"])
    if len(images) != 1:
        raise LonoraError("skill_package_validation_required", 409)
    return next(iter(images))


class PackageState(Contract):
    kind: str = "skill-package-v1"
    versions: list[PackageVersion] = Field(min_length=1, max_length=8)


def validate_package_files(entry: PackageVersion, files: dict[str, bytes]) -> None:
    if any(
        path not in files or hashlib.sha256(files[path]).hexdigest() != digest
        for path, digest in entry.files.items()
    ):
        raise LonoraError("skill_package_source_changed", 409)


def read_state(state: dict[str, Any]) -> PackageState:
    from pydantic import ValidationError

    try:
        value = PackageState.model_validate(state.get("package"))
    except ValidationError:
        raise LonoraError("skill_package_state_invalid", 409) from None
    if value.kind != "skill-package-v1":
        raise LonoraError("skill_package_state_invalid", 409)
    return value


def package_payload(
    identity: str,
    version: str,
    content: str,
    utilities: list[str],
    *,
    source: Literal["external", "installed"],
) -> AgentSkill:
    description, _ = skill_document(content, identity, required=True)
    return AgentSkill(
        name=identity,
        content=content,
        enabled=False,
        manifest=SkillManifest(
            id=identity,
            version=version,
            title=identity,
            description=description,
            source=source,
            stability="experimental",
            activation=SkillActivation(mode="explicit"),
            risk_class="state_mutating" if utilities else "read_only",
            required_tools=["workspace_read", "workspace_execute"] if utilities else [],
            context_budget=16000,
        ),
    )


def decode_package_text(body: bytes) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeError:
        raise LonoraError("skill_package_binary_unsupported", 422) from None
    if any((ord(char) < 32 and char not in "\t\r\n") or ord(char) == 127 for char in text):
        raise LonoraError("skill_package_binary_unsupported", 422)
    return text


def prepare_workspace_package(
    snapshot: dict[str, bytes],
    *,
    agent_id: str,
    run_id: str,
    workspace_revision: int,
    source_directory: str,
    version: str,
    adapted_content: str,
    review: AdaptationReview,
) -> tuple[PackageVersion, dict[str, str]]:
    from ..workspace import encode_snapshot

    TypeAdapter(SkillVersion).validate_python(version)
    # The same lexical/file bounds used by reads and execution apply here. No
    # host path is opened and no caller-selected Agent or snapshot is accepted.
    encode_snapshot(snapshot)
    source_path = f"{source_directory}/SKILL.md"
    encode_snapshot({source_path: b""})
    directory = PurePosixPath(source_directory)
    source_files = {
        name: body
        for name, body in snapshot.items()
        if PurePosixPath(name).is_relative_to(directory)
    }
    if source_path not in source_files:
        raise LonoraError("skill_package_document_missing", 422)
    if len(source_files) > 64 or sum(map(len, source_files.values())) > 1048576:
        raise LonoraError("skill_package_too_large", 422)
    if any(len(body) > 262144 for body in source_files.values()):
        raise LonoraError("skill_package_file_too_large", 422)
    if any(PurePosixPath(name).name == "SKILL.md" and name != source_path for name in source_files):
        raise LonoraError("skill_package_nested_unsupported", 422)
    texts = {name: decode_package_text(body) for name, body in source_files.items()}
    original = texts[source_path]
    if len(original.encode()) > 64000:
        raise LonoraError("skill_document_too_large", 422)
    match = FRONTMATTER.match(original)
    if match is None or len(match[1]) > 8000:
        raise LonoraError("skill_frontmatter_invalid", 422)
    try:
        metadata: object = yaml.safe_load(match[1])
        identity = (
            cast(dict[str, Any], metadata).get("name") if isinstance(metadata, dict) else None
        )
        if not isinstance(identity, str):
            raise ValueError()
        validate_skill_name(identity)
        skill_document(original, identity, required=True)
    except (yaml.YAMLError, RecursionError, ValueError):
        raise LonoraError("skill_frontmatter_invalid", 422) from None
    prefix = f"skills/{identity}/{version}"
    selected = {
        f"{prefix}/{PurePosixPath(name).relative_to(directory)}": body
        for name, body in texts.items()
    }
    encode_snapshot({name: body.encode() for name, body in selected.items()})
    inspected = inspect_utilities(source_files)
    utilities = [
        f"{prefix}/{PurePosixPath(item['path']).relative_to(directory)}" for item in inspected
    ]
    return (
        PackageVersion(
            payload=package_payload(
                identity, version, adapted_content, utilities, source="installed"
            ),
            source_kind="workspace",
            workspace_source=WorkspaceSource(
                agent_id=agent_id,
                run_id=run_id,
                workspace_revision=workspace_revision,
                source_directory=source_directory,
                snapshot_sha256=hashlib.sha256(encode_snapshot(source_files)).hexdigest(),
            ),
            source_path=source_path,
            source_sha256=hashlib.sha256(source_files[source_path]).hexdigest(),
            files={
                name: hashlib.sha256(body.encode()).hexdigest() for name, body in selected.items()
            },
            utilities=utilities,
            external_imports={
                f"{prefix}/{PurePosixPath(item['path']).relative_to(directory)}": item["imports"]
                for item in inspected
            },
            license_files={
                name: hashlib.sha256(body).hexdigest()
                for name, body in source_files.items()
                if PurePosixPath(name).name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
            },
            review=review,
        ),
        selected,
    )


async def fetch_package(url: str, commit: str) -> bytes:
    owner, repository = repository_identity(url)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise LonoraError("skill_package_commit_required", 422)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            return await read_public_source(
                client,
                f"https://codeload.github.com/{owner}/{repository}/zip/{commit}",
                maximum=MAX_ARCHIVE_BYTES,
            )
    except httpx.HTTPError:
        raise LonoraError("skill_repository_unavailable", 502) from None


def prepare_package(
    archive: bytes,
    *,
    repository_url: str,
    commit: str,
    source_path: str,
    version: str,
    adapted_content: str,
    review: AdaptationReview,
) -> tuple[PackageVersion, dict[str, str]]:
    from ..workspace import encode_snapshot

    TypeAdapter(SkillVersion).validate_python(version)
    _, repository = repository_identity(repository_url)
    report = inspect_archive(archive, repository=repository, commit=commit)
    source = next((item for item in report["skills"] if item["path"] == source_path), None)
    if source is None or not source["format_compatible"]:
        raise LonoraError("skill_package_document_incompatible", 422)
    identity = str(source["id"])
    skill_document(adapted_content, identity, required=True)
    files = archive_files(archive)
    directory = PurePosixPath(source_path).parent
    prefix = f"skills/{identity}/{version}"
    selected: dict[str, str] = {}
    for name, body in sorted(files.items()):
        path = PurePosixPath(name)
        if not path.is_relative_to(directory):
            continue
        # Other nested Skills are separate packages; do not install them implicitly.
        relative = path.relative_to(directory)
        if any(
            (directory / PurePosixPath(*relative.parts[:index]) / "SKILL.md").as_posix() in files
            for index in range(1, len(relative.parts))
        ):
            continue
        if len(body) > 262144:
            raise LonoraError("skill_package_file_too_large", 422)
        selected[f"{prefix}/{relative}"] = decode_package_text(body)
    for license_file in report["license_files"]:
        name = license_file["path"]
        if PurePosixPath(name).is_relative_to(directory):
            continue
        selected[f"{prefix}/_source_licenses/{name}"] = decode_package_text(files[name])
    if (
        not selected
        or len(selected) > 64
        or sum(len(body.encode()) for body in selected.values()) > 1048576
    ):
        raise LonoraError("skill_package_too_large", 422)
    encode_snapshot({path: body.encode() for path, body in selected.items()})
    utilities = [
        f"{prefix}/{PurePosixPath(item['path']).relative_to(directory)}"
        for item in report["utilities"]
        if item["path"] in source["utilities"]
        and f"{prefix}/{PurePosixPath(item['path']).relative_to(directory)}" in selected
    ]
    payload = package_payload(identity, version, adapted_content, utilities, source="external")
    return (
        PackageVersion(
            payload=payload,
            repository_url=repository_url,
            commit=commit,
            archive_sha256=report["archive_sha256"],
            source_path=source_path,
            source_sha256=source["sha256"],
            license_files={item["path"]: item["sha256"] for item in report["license_files"]},
            files={
                path: hashlib.sha256(body.encode()).hexdigest() for path, body in selected.items()
            },
            utilities=utilities,
            external_imports={
                f"{prefix}/{PurePosixPath(item['path']).relative_to(directory)}": item["imports"]
                for item in report["utilities"]
                if item["path"] in source["utilities"]
            },
            unmaterialized_dependencies=[
                name
                for name in report["dependency_files"]
                if not PurePosixPath(name).is_relative_to(directory)
            ],
            review=review,
        ),
        selected,
    )
