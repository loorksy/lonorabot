"""Bounded, immutable inspection of public Skill packages; never execute source."""

import ast
import hashlib
import json
import re
import stat
import sys
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, cast
from urllib.parse import quote, urlsplit
from zipfile import BadZipFile, ZipFile

import httpx
from lonora_core.agent_skill import validate_skill_name
from lonora_core.user_error import LonoraError

from .document import skill_document

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_FILES = 512
MAX_SOURCE_BYTES = 512 * 1024
SCRIPT_SUFFIXES = frozenset({".py", ".sh", ".bash", ".js", ".ts"})


def repository_identity(url: str) -> tuple[str, str]:
    value = urlsplit(url)
    parts = value.path.strip("/").split("/")
    if (
        value.scheme != "https"
        or value.netloc != "github.com"
        or value.query
        or value.fragment
        or len(parts) != 2
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", parts[0])
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", parts[1])
    ):
        raise LonoraError("skill_repository_url_invalid", 422)
    owner, repository = parts
    repository = repository.removesuffix(".git")
    if not repository or repository in {".", ".."}:
        raise LonoraError("skill_repository_url_invalid", 422)
    return owner, repository


def archive_files(content: bytes) -> dict[str, bytes]:
    """One bounded archive reader shared by inspection and owned import."""
    if len(content) > MAX_ARCHIVE_BYTES:
        raise LonoraError("skill_repository_archive_invalid", 422)
    files: dict[str, bytes] = {}
    size = 0
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES * 2:
                raise LonoraError("skill_repository_archive_too_large", 422)
            root: str | None = None
            for member in members:
                path = PurePosixPath(member.filename)
                if (
                    path.is_absolute()
                    or len(member.filename) > 512
                    or len(path.parts) > 16
                    or ".." in path.parts
                    or "\\" in member.filename
                    or not path.parts
                    or stat.S_ISLNK(member.external_attr >> 16)
                    or (root is not None and path.parts[0] != root)
                ):
                    raise LonoraError("skill_repository_path_unsafe", 422)
                root = path.parts[0]
                if member.is_dir():
                    continue
                if len(path.parts) < 2:
                    raise LonoraError("skill_repository_path_unsafe", 422)
                relative = str(PurePosixPath(*path.parts[1:]))
                size += member.file_size
                if size > MAX_ARCHIVE_BYTES or len(files) >= MAX_FILES:
                    raise LonoraError("skill_repository_archive_too_large", 422)
                if relative in files:
                    raise LonoraError("skill_repository_path_duplicate", 422)
                # Never extract repository-controlled paths into the host filesystem.
                files[relative] = archive.read(member)
    except (BadZipFile, RuntimeError, OSError, ValueError):
        raise LonoraError("skill_repository_archive_invalid", 422) from None
    return files


def inspect_archive(content: bytes, *, repository: str, commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise LonoraError("skill_repository_archive_invalid", 422)
    files = archive_files(content)

    scripts: list[dict[str, Any]] = []
    for name, body in sorted(files.items()):
        path = PurePosixPath(name)
        if path.suffix not in SCRIPT_SUFFIXES or "tests" in path.parts:
            continue
        imports: set[str] = set()
        code: str | None = "skill_source_language_not_validated" if path.suffix != ".py" else None
        if len(body) > MAX_SOURCE_BYTES:
            code = "skill_source_too_large"
        elif path.suffix == ".py":
            try:
                tree = ast.parse(body.decode("utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.update(item.name.split(".")[0] for item in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                        imports.add(node.module.split(".")[0])
            except (SyntaxError, UnicodeError, ValueError, RecursionError):
                code = "skill_source_invalid"
        scripts.append(
            {
                "path": name,
                "sha256": hashlib.sha256(body).hexdigest(),
                "imports": sorted(imports - sys.stdlib_module_names)[:64],
                "code": code,
            }
        )

    skills: list[dict[str, Any]] = []
    for name, body in sorted(files.items()):
        path = PurePosixPath(name)
        if path.name != "SKILL.md":
            continue
        identity = path.parent.name if str(path.parent) != "." else repository
        description = ""
        code = None
        if len(body) > 64000:
            code = "skill_document_too_large"
        else:
            try:
                validate_skill_name(identity)
                description, _ = skill_document(body.decode("utf-8"), identity, required=True)
            except UnicodeError:
                code = "skill_frontmatter_invalid"
            except LonoraError as error:
                code = error.code
        utilities = [
            item["path"]
            for item in scripts
            if PurePosixPath(item["path"]).is_relative_to(path.parent)
        ]
        skills.append(
            {
                "id": identity,
                "path": name,
                "description": description,
                "sha256": hashlib.sha256(body).hexdigest(),
                "format_compatible": code is None,
                "code": code,
                "utilities": utilities,
                "requires_isolated_execution": bool(utilities),
                "adaptation_status": "review_required",
            }
        )
    return {
        "repository": repository,
        "commit": commit,
        "archive_sha256": hashlib.sha256(content).hexdigest(),
        "file_count": len(files),
        "skills": skills,
        "utilities": scripts,
        "dependency_files": sorted(
            name
            for name in files
            if PurePosixPath(name).name
            in {"requirements.txt", "pyproject.toml", "package.json", "uv.lock", "poetry.lock"}
        ),
        "license_files": [
            {"path": name, "sha256": hashlib.sha256(body).hexdigest()}
            for name, body in sorted(files.items())
            if PurePosixPath(name).name.upper()
            in {"LICENSE", "LICENSE.MD", "LICENSE.TXT", "COPYING", "NOTICE"}
        ],
        "validation_level": "static_inspection_only",
        "installed": False,
        "code_executed": False,
        "authority_granted": False,
        "instrument_mapping": "not_performed; broker symbols and source compatibility require explicit validation",
        "limitations": [
            "dependency_imports_are_not_pinned_package_requirements",
            "dynamic_dependencies_not_resolved",
            "static_inspection_is_not_security_approval",
            "scripts_require_isolated_execution_before_activation",
        ],
    }


async def inspect_repository(
    url: str, ref: str, *, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    owner, repository = repository_identity(url)
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,120}", ref) or any(
        part in {"", ".", ".."} for part in ref.split("/")
    ):
        raise LonoraError("skill_repository_ref_invalid", 422)
    owned_client = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=False)
    try:
        commit: Any = ref if re.fullmatch(r"[0-9a-f]{40}", ref) else None
        if commit is None:
            # Commit detail responses include complete file patches. The listing
            # resolves refs without downloading an unrelated, potentially huge diff.
            body = await read_public_source(
                client,
                f"https://api.github.com/repos/{owner}/{repository}/commits?sha={quote(ref, safe='')}&per_page=1",
                maximum=MAX_SOURCE_BYTES,
            )
            decoded: Any = json.loads(body)
            records = cast(list[Any], decoded) if isinstance(decoded, list) else []
            record: Any = records[0] if len(records) == 1 else None
            commit = cast(dict[str, Any], record).get("sha") if isinstance(record, dict) else None
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise LonoraError("skill_repository_revision_invalid", 502)
        data = await read_public_source(
            client,
            f"https://codeload.github.com/{owner}/{repository}/zip/{commit}",
            maximum=MAX_ARCHIVE_BYTES,
        )
        result = inspect_archive(data, repository=repository, commit=commit)
        return {**result, "repository_url": f"https://github.com/{owner}/{repository}"}
    except (httpx.HTTPError, ValueError, AttributeError):
        raise LonoraError("skill_repository_unavailable", 502) from None
    finally:
        if owned_client:
            await client.aclose()


async def read_public_source(client: httpx.AsyncClient, url: str, *, maximum: int) -> bytes:
    async with client.stream("GET", url, follow_redirects=False) as response:
        if response.status_code == 404:
            raise LonoraError("skill_repository_not_found", 404)
        if response.status_code == 429 or (
            response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise LonoraError("skill_repository_rate_limited", 429)
        if response.status_code == 403:
            raise LonoraError("skill_repository_access_denied", 403)
        if not response.is_success:
            raise LonoraError("skill_repository_unavailable", 502)
        data = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=65536):
            if len(data) + len(chunk) > maximum:
                raise LonoraError("skill_repository_archive_too_large", 422)
            data.extend(chunk)
        return bytes(data)
