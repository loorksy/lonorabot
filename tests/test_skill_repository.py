"""Untrusted repository inspection must remain bounded and non-executing."""

import hashlib
import stat
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import httpx
import pytest
from lonora_agent.skills.repository import (
    MAX_ARCHIVE_BYTES,
    inspect_archive,
    inspect_repository,
    repository_identity,
)
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools

COMMIT = "a" * 40
DOCUMENT = "---\nname: sample\ndescription: Inspect historical prices.\n---\n# Sample\nUse verified data.\n"


def archive(files: dict[str, str | bytes]) -> bytes:
    result = BytesIO()
    with ZipFile(result, "w", compression=ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr("repository-commit/" + name, content)
    return result.getvalue()


def test_inspection_reports_provenance_without_running_source(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist"
    source = f"import json\nimport numpy\nfrom pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n"
    content = archive(
        {
            "sample/SKILL.md": DOCUMENT,
            "sample/analyze.py": source,
            "requirements.txt": "numpy==2.2.0\n",
            "tests/test_sample.py": "raise RuntimeError('must not run tests')",
        }
    )
    result = inspect_archive(content, repository="example", commit=COMMIT)
    assert not sentinel.exists()
    assert result["commit"] == COMMIT
    assert result["archive_sha256"] == hashlib.sha256(content).hexdigest()
    assert result["installed"] is result["code_executed"] is result["authority_granted"] is False
    assert result["dependency_files"] == ["requirements.txt"]
    assert result["utilities"] == [
        {
            "path": "sample/analyze.py",
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
            "imports": ["numpy"],
            "code": None,
        }
    ]
    skill = result["skills"][0]
    assert skill["format_compatible"]
    assert skill["requires_isolated_execution"]
    assert skill["adaptation_status"] == "review_required"
    assert skill["utilities"] == ["sample/analyze.py"]


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://github.com.evil.test/owner/repo",
        "https://github.com@127.0.0.1/owner/repo",
        "https://owner:secret@github.com/owner/repo",
        "https://github.com/owner/repo?access_token=private",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner/..",
        "https://github.com/owner/%2e%2e",
        "https://127.0.0.1/owner/repo",
    ],
)
def test_only_public_github_repository_identity_is_accepted(url: str) -> None:
    with pytest.raises(LonoraError, match="skill_repository_url_invalid"):
        repository_identity(url)


def test_canonical_repository_suffix() -> None:
    assert repository_identity("https://github.com/owner/repository.git/") == (
        "owner",
        "repository",
    )


@pytest.mark.parametrize(
    "name", ["../escape", "sample/../../escape", "/absolute", "sample\\escape"]
)
def test_unsafe_archive_members_are_rejected(name: str) -> None:
    content = BytesIO()
    with ZipFile(content, "w") as bundle:
        bundle.writestr(name if name.startswith("/") else "root/" + name, "unsafe")
    with pytest.raises(LonoraError, match="skill_repository_path_unsafe"):
        inspect_archive(content.getvalue(), repository="example", commit=COMMIT)


def test_symlink_archive_member_is_rejected() -> None:
    content = BytesIO()
    with ZipFile(content, "w") as bundle:
        entry = ZipInfo("root/sample/link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(entry, "/etc/passwd")
    with pytest.raises(LonoraError, match="skill_repository_path_unsafe"):
        inspect_archive(content.getvalue(), repository="example", commit=COMMIT)


def test_expanded_archive_budget_is_enforced_before_reading() -> None:
    content = archive({"large.bin": b"x" * (MAX_ARCHIVE_BYTES + 1)})
    with pytest.raises(LonoraError, match="skill_repository_archive_too_large"):
        inspect_archive(content, repository="example", commit=COMMIT)


def test_invalid_instructions_and_python_are_reported_without_activation() -> None:
    content = archive(
        {"sample/SKILL.md": "---\nname: another\n---\nWrong identity", "sample/broken.py": "def :"}
    )
    result = inspect_archive(content, repository="example", commit=COMMIT)
    assert not result["skills"][0]["format_compatible"]
    assert result["skills"][0]["code"] == "skill_frontmatter_invalid"
    assert result["utilities"][0]["code"] == "skill_source_invalid"
    assert not result["installed"]


@pytest.mark.asyncio
async def test_public_request_resolves_one_commit_and_downloads_only_that_archive() -> None:
    paths: list[str] = []
    content = archive({"sample/SKILL.md": DOCUMENT})

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(str(request.url))
        assert "Authorization" not in request.headers
        if request.url.host == "api.github.com":
            assert request.url.path == "/repos/owner/repository/commits"
            assert dict(request.url.params) == {"sha": "main", "per_page": "1"}
            return httpx.Response(200, json=[{"sha": COMMIT}])
        assert str(request.url) == f"https://codeload.github.com/owner/repository/zip/{COMMIT}"
        return httpx.Response(200, content=content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await inspect_repository(
            "https://github.com/owner/repository.git", "main", client=client
        )
    assert len(paths) == 2
    assert result["repository_url"] == "https://github.com/owner/repository"
    assert result["commit"] == COMMIT
    assert not result["code_executed"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (404, "skill_repository_not_found"),
        (403, "skill_repository_access_denied"),
        (429, "skill_repository_rate_limited"),
        (503, "skill_repository_unavailable"),
    ],
)
async def test_public_request_failure_stays_explicit(status: int, code: str) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status))
    ) as client:
        with pytest.raises(LonoraError, match=code):
            await inspect_repository("https://github.com/owner/repository", "main", client=client)


def test_repository_inspection_is_a_read_only_nonfinancial_tool() -> None:
    tool = load_tools().tools["skill_repository_inspect"]
    assert tool.read_only and not tool.financial


@pytest.mark.asyncio
async def test_redirects_never_reach_another_host() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(LonoraError, match="skill_repository_unavailable"):
            await inspect_repository("https://github.com/owner/repository", "main", client=client)
    assert len(requests) == 1
