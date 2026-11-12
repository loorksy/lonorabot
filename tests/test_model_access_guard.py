"""Guard for mandate 12.2 and P4: model access stays on API keys and one engine.

Lonora's own code and deployment (every tracked file under packages, apps, scripts,
infra and tests, and the root build and deployment files) must not contain:

- a subscription login or OAuth token flow of an AI platform (Claude Pro/Max/Ultra,
  ChatGPT, Grok or others);
- another vendor's CLI client id;
- a call to a private vendor endpoint, and no model adapter calls a host other than
  the providers' public API hosts or the owner's own endpoint;
- an import, dependency or invocation of Claude Code, the Claude Agent SDK or another
  agent harness as Lonora's engine.

Out of scope, by the mandate's own text: command-line tools an agent installs and runs
in its workspace with keys the owner provided (12.2, 7.1). Prose (Markdown prompts,
skills and documents) may name such tools, so only code, configuration and dependency
files are scanned. Also out of scope: the repository's own development tooling for
the people building Lonora (``.claude/``), and the vendored TradingView library.
"""

import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from lonora_core.model_providers import PROVIDER_URLS
from lonora_providers.registry import PROVIDERS

ROOT = Path(__file__).resolve().parents[1]
THIS = Path(__file__).resolve().relative_to(ROOT).as_posix()
SCANNED_DIRECTORIES = ("packages/", "apps/", "scripts/", "infra/", "tests/")
SCANNED_ROOT_FILES = {
    "Dockerfile",
    "docker-compose.yml",
    "entrypoint.sh",
    "pyproject.toml",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    ".env.example",
}
CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".ini",
    ".cfg",
    ".txt",
    ".example",
    ".conf",
}
EXCLUDED = ("apps/web/public/charting_library/",)

# Public API hosts of the providers 12.1 names. The owner's OpenAI-compatible endpoint,
# when present, is the owner's own URL and is not listed here.
PUBLIC_MODEL_HOSTS = {
    "api.anthropic.com",
    "api.openai.com",
    "api.deepseek.com",
    "openrouter.ai",
    "api.z.ai",
}

RULES: dict[str, tuple[str, ...]] = {
    "AI-platform subscription login or OAuth token": (
        r"sk-ant-o[ar]t",  # Claude subscription OAuth access and refresh tokens
        r"CLAUDE_CODE_OAUTH_TOKEN",
        r"setup-token",
        r"\boauth-20\d\d-\d\d-\d\d\b",  # the anthropic-beta flag of subscription tokens
        r"claude\.ai/(oauth|api|login)",
        r"console\.anthropic\.com/(v1/)?oauth",
        r"auth\.openai\.com",
        r"chatgpt\.com",
        r"chat\.openai\.com",
        r"(accounts|auth)\.x\.ai",
        r"grok\.com",
        r"\bOPENAI_ACCESS_TOKEN\b|\bCHATGPT_(ACCESS|SESSION)_TOKEN\b",
    ),
    "another vendor's CLI client id": (
        r"9d1c250a-e61b-44d9-88ed-5944d1962f5e",  # Claude Code
        r"app_EMoamEEZ73f0CkXaXp7hrann",  # Codex CLI
        r"681255809395-[a-z0-9]+\.apps\.googleusercontent\.com",  # Gemini CLI
    ),
    "private vendor endpoint": (
        r"/backend-api/",
        r"api\.claude\.ai",
        r"cloudcode-pa\.googleapis\.com",
    ),
    "Claude Code, the Claude Agent SDK or another agent harness as the engine": (
        r"\bclaude[_-]agent[_-]sdk\b",
        r"\bclaude[_-]code[_-]sdk\b",
        r"@anthropic-ai/claude-(code|agent-sdk)",
        r"@openai/codex",
        r"\bopenai[_-]agents\b",
        r"@openai/agents",
        r"\blanggraph\b",
        r"\bcrewai\b",
        r"\bautogen[_-]agentchat\b",
        # The claude or codex binary started as a process: an argv, a lookup or a shell line.
        r"""[\[(]\s*["'](claude|codex)["']\s*[,)\]]""",
        r"""which\(\s*["'](claude|codex)["']""",
        r"(^|[;&|]\s*|\bexec\s+|\bnpx\s+)(claude|codex)\s+(-p|--print|exec)\b",
    ),
}
PATTERNS = [
    (kind, re.compile(pattern, re.IGNORECASE | re.MULTILINE))
    for kind, patterns in RULES.items()
    for pattern in patterns
]


def scanned_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode()
    result: list[str] = []
    for path in filter(None, listed.split("\0")):
        if path == THIS or path.startswith(EXCLUDED):
            continue
        name = Path(path).name
        in_scope = path in SCANNED_ROOT_FILES or path.startswith(SCANNED_DIRECTORIES)
        is_code = Path(path).suffix in CODE_SUFFIXES or name in {"Dockerfile", "Caddyfile"}
        if in_scope and is_code and (ROOT / path).is_file():
            result.append(path)
    return result


def test_the_scan_covers_lonoras_code_and_deployment() -> None:
    files = set(scanned_files())
    for expected in (
        "packages/adapters/src/lonora_adapters/models/anthropic.py",
        "packages/providers/src/lonora_providers/router.py",
        "packages/agent-runtime/src/lonora_agent/workspace.py",
        "apps/web/package.json",
        "apps/mobile/package.json",
        "pyproject.toml",
        "pnpm-lock.yaml",
        "Dockerfile",
        "docker-compose.yml",
        "entrypoint.sh",
    ):
        assert expected in files, expected
    assert len(files) > 500


@pytest.mark.parametrize(
    ("kind", "sample"),
    [
        ("AI-platform subscription login or OAuth token", 'TOKEN = "sk-ant-oat01-abc"'),
        ("AI-platform subscription login or OAuth token", '"anthropic-beta": "oauth-2025-04-20"'),
        ("AI-platform subscription login or OAuth token", "url = 'https://chatgpt.com/x'"),
        ("another vendor's CLI client id", 'CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"'),
        ("private vendor endpoint", 'BASE = "https://chatgpt.example/backend-api/codex"'),
        (
            "Claude Code, the Claude Agent SDK or another agent harness as the engine",
            "from claude_agent_sdk import query",
        ),
        (
            "Claude Code, the Claude Agent SDK or another agent harness as the engine",
            '"@anthropic-ai/claude-agent-sdk": "^0.1.0"',
        ),
        (
            "Claude Code, the Claude Agent SDK or another agent harness as the engine",
            'subprocess.run(["claude", "-p", prompt])',
        ),
        (
            "Claude Code, the Claude Agent SDK or another agent harness as the engine",
            'exec claude --print "$PROMPT"',
        ),
        (
            "Claude Code, the Claude Agent SDK or another agent harness as the engine",
            'shutil.which("codex")',
        ),
    ],
)
def test_each_rule_catches_what_it_names(kind: str, sample: str) -> None:
    assert any(found == kind and pattern.search(sample) for found, pattern in PATTERNS)


@pytest.mark.parametrize(
    "sample",
    [
        'model = "gpt-5-codex"',  # a model id served through the public API
        'model = "claude-sonnet-4-5"',
        "https://api.anthropic.com/v1/messages",
        "authorization_url(endpoint, client_id)",  # the generic MCP OAuth helper
    ],
)
def test_ordinary_api_use_is_not_flagged(sample: str) -> None:
    assert not any(pattern.search(sample) for _, pattern in PATTERNS)


def test_lonoras_code_has_no_subscription_login_private_endpoint_or_other_engine() -> None:
    findings: list[str] = []
    for path in scanned_files():
        text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path}:{line}: {kind}: {match.group(0)!r}")
    assert not findings, "\n".join(findings)


def test_every_model_adapter_calls_a_public_api_host() -> None:
    hosts = {urlsplit(url).hostname for url in PROVIDER_URLS.values()}
    assert hosts == PUBLIC_MODEL_HOSTS
    for provider, adapter in PROVIDERS.items():
        if provider == "openai_compatible":
            continue  # the owner's own base URL, checked when it is configured
        instance = adapter("fixture-not-a-real-key")
        assert urlsplit(instance.base_url).hostname in PUBLIC_MODEL_HOSTS, provider
        assert urlsplit(instance.base_url).scheme == "https", provider


def test_every_model_host_in_the_adapters_is_public() -> None:
    adapters = ROOT / "packages/adapters/src/lonora_adapters"
    for path in [*adapters.glob("models/*.py"), *adapters.glob("voice/*.py")]:
        for host in re.findall(r"(?:https|wss)://([a-z0-9.-]+)", path.read_text()):
            assert host in PUBLIC_MODEL_HOSTS, f"{path.relative_to(ROOT)}: {host}"
