"""Bounded pinned packages and adaptation records, never publisher authority."""

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

import httpx
from lonora_contracts.domain import Contract
from lonora_contracts.skills import AgentSkill, SkillActivation, SkillManifest, SkillVersion
from lonora_core.user_error import LonoraError
from lonora_tools.skills import SkillAdaptationReview as AdaptationReview
from pydantic import Field, TypeAdapter

from .document import skill_document
from .repository import (
    MAX_ARCHIVE_BYTES,
    archive_files,
    inspect_archive,
    read_public_source,
    repository_identity,
)


class PackageVersion(Contract):
    payload: AgentSkill
    repository_url: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_path: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_files: dict[str, str] = Field(default_factory=dict, max_length=32)
    files: dict[str, str] = Field(max_length=64)
    utilities: list[str] = Field(max_length=64)
    external_imports: dict[str, list[str]] = Field(default_factory=dict, max_length=64)
    unmaterialized_dependencies: list[str] = Field(default_factory=list, max_length=64)
    review: AdaptationReview
    validation: dict[str, Any] | None = None


class PackageState(Contract):
    kind: str = "skill-package-v1"
    versions: list[PackageVersion] = Field(min_length=1, max_length=8)


def read_state(state: dict[str, Any]) -> PackageState:
    from pydantic import ValidationError

    try:
        value = PackageState.model_validate(state.get("package"))
    except ValidationError:
        raise LonoraError("skill_package_state_invalid", 409) from None
    if value.kind != "skill-package-v1":
        raise LonoraError("skill_package_state_invalid", 409)
    return value


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
    description, _ = skill_document(adapted_content, identity, required=True)
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
        try:
            selected[f"{prefix}/{relative}"] = body.decode("utf-8")
        except UnicodeError:
            raise LonoraError("skill_package_binary_unsupported", 422) from None
    for license_file in report["license_files"]:
        name = license_file["path"]
        if PurePosixPath(name).is_relative_to(directory):
            continue
        try:
            selected[f"{prefix}/_source_licenses/{name}"] = files[name].decode("utf-8")
        except UnicodeError:
            raise LonoraError("skill_package_binary_unsupported", 422) from None
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
    payload = AgentSkill(
        name=identity,
        content=adapted_content,
        enabled=False,
        manifest=SkillManifest(
            id=identity,
            version=version,
            title=identity,
            description=description,
            source="external",
            stability="experimental",
            activation=SkillActivation(mode="explicit"),
            risk_class="state_mutating" if utilities else "read_only",
            required_tools=["workspace_read", "workspace_execute"] if utilities else [],
            context_budget=16000,
        ),
    )
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
