"""Guard for mandate 12.2 and P4: model access stays on API keys and one engine.

Lonora's own code and deployment must not contain:

- a subscription login or OAuth token flow of an AI platform (Claude Pro/Max/Ultra,
  ChatGPT, Grok or others), including reading another client's stored login;
- another vendor's CLI client id;
- a call to a private vendor endpoint, and no model adapter calls a host other than
  the providers' public API hosts or the owner's own endpoint;
- Claude Code, the Claude Agent SDK or another agent harness as Lonora's engine: an
  import, a dependency of Lonora's own packages, or a process start of the ``claude``
  or ``codex`` CLI in its non-interactive engine mode (``-p``, ``--print``, ``exec``).

What is scanned: every tracked text file under packages, apps, scripts, infra and
tests, and every tracked text file at the repository root, except Markdown (prose:
prompts, skills and documents may name the tools an agent may use) and the vendored
TradingView library. Not scanned: ``.claude/`` and ``docs/``, the builders' own
tooling and documents, which are not Lonora's code or deployment.

Out of scope, by the mandate's own text (12.2, 7.1): command-line tools an agent
installs and runs in its workspace with keys the owner provided. So installing or
checking a CLI (``npm i -g @anthropic-ai/claude-code``, ``claude --version``) is not a
finding; only running one as Lonora's engine is. A program name held in a variable
cannot be recognized from text; that limit is accepted.
"""

import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from lonora_adapters.models.base import BaseModelAdapter
from lonora_core.model_providers import PROVIDER_URLS
from lonora_providers.registry import PROVIDERS

ROOT = Path(__file__).resolve().parents[1]
THIS = Path(__file__).resolve().relative_to(ROOT).as_posix()
SCANNED_DIRECTORIES = ("packages/", "apps/", "scripts/", "infra/", "tests/")
PROSE = {".md", ".mdx", ".rst"}
EXCLUDED = ("apps/web/public/charting_library/",)
# Lonora's own dependency manifests and locks (its packages, apps and deployment
# images): a harness listed here would be part of its engine.
DEPENDENCY_FILES = re.compile(
    r"(^|/)(pyproject\.toml|package\.json|pnpm-lock\.yaml|requirements[^/]*\.txt|[^/]*\.lock)$"
)

# Public API hosts of the providers 12.1 names. The owner's OpenAI-compatible endpoint,
# when present, is the owner's own URL and is not listed here.
PUBLIC_MODEL_HOSTS = {
    "api.anthropic.com",
    "api.openai.com",
    "api.deepseek.com",
    "openrouter.ai",
    "api.z.ai",
}

LOGIN = "AI-platform subscription login or OAuth token"
CLIENT_ID = "another vendor's CLI client id"
PRIVATE = "private vendor endpoint"
ENGINE = "Claude Code, the Claude Agent SDK or another agent harness as the engine"

RULES: dict[str, tuple[str, ...]] = {
    LOGIN: (
        r"sk-ant-o[ar]t",  # Claude subscription OAuth access and refresh tokens
        r"CLAUDE_CODE_OAUTH_TOKEN",
        r"ANTHROPIC_AUTH_TOKEN",
        r"anthropic[^\n]*\bauth_token\s*=|\bauth_token\s*=[^\n]*anthropic",
        r"\bclaude\s+setup-token\b",
        r"\boauth-20\d\d-\d\d-\d\d\b",  # the anthropic-beta flag of subscription tokens
        r"\bclaude-code-20\d{6}\b",  # the beta flag Claude Code's own client sends
        r"(claude\.ai|claude\.com|anthropic\.com)/\S*oauth",
        r"claude\.ai/(api|login)\b",
        r"\.claude/\.credentials\.json|claudeAiOauth|Claude Code-credentials",
        r"""["']\.credentials\.json["']""",  # the same file joined from parts
        r"\.codex/auth\.json",
        r"auth\.openai\.com",
        r"(chatgpt\.com|chat\.openai\.com)/(backend-api|auth|api/auth)",
        r"(accounts|auth)\.x\.ai",
        r"grok\.com/(rest|api)",
        r"\bOPENAI_ACCESS_TOKEN\b|\bCHATGPT_(ACCESS|SESSION)_TOKEN\b",
    ),
    CLIENT_ID: (
        r"9d1c250a-e61b-44d9-88ed-5944d1962f5e",  # Claude Code
        r"app_EMoamEEZ73f0CkXaXp7hrann",  # Codex CLI
        r"681255809395-[a-z0-9]+\.apps\.googleusercontent\.com",  # Gemini CLI
    ),
    PRIVATE: (
        r"/backend-api/",
        r"api\.claude\.ai",
        r"cloudcode-pa\.googleapis\.com",
    ),
    ENGINE: (
        r"^\s*(from|import)\s+(claude_agent_sdk|claude_code_sdk|langgraph|crewai|autogen_agentchat)\b",
        r"""(from|require\(|import\()\s*["'](@anthropic-ai/claude-(code|agent-sdk)|@openai/codex(-sdk)?|@openai/agents)""",
        # A name bound to the program, so that argv[0] in a variable is still found.
        r"""\b\w+\s*[:=]\s*["'](?:[\w./-]*/)?(claude|codex)["']""",
    ),
}
PATTERNS = [
    (kind, re.compile(pattern, re.IGNORECASE | re.MULTILINE))
    for kind, patterns in RULES.items()
    for pattern in patterns
]
HARNESS_DEPENDENCY = re.compile(
    r"""(?:^|["'\s/])(claude[-_]agent[-_]sdk|claude[-_]code[-_]sdk|@anthropic-ai/claude-(code|agent-sdk)"""
    r"""|@openai/codex(-sdk)?|openai-agents|@openai/agents|langgraph|crewai|autogen-agentchat)\b""",
    re.IGNORECASE | re.MULTILINE,
)
# A process start: Python, Node and shell forms.
PROCESS_START = re.compile(
    r"\b(subprocess\.\w+|create_subprocess_\w+|os\.system|os\.exec\w*|os\.spawn\w*|os\.popen"
    r"|execSync|execFileSync|execFile|spawnSync|spawn|execa|exec)\s*\(",
)
ENGINE_COMMAND = re.compile(
    r"""(?<![\w-])(?:[\w./-]*/)?(claude|codex)["',\s]+(?:[^;\n]{0,80}?[\s"',])?(-p|--print|exec)\b"""
)
SHELL_ENGINE = re.compile(
    r"(^|[;&|=]\s*|\bexec\s+|\bnpx\s+|\$\(\s*)(?:[\w./-]*/)?(claude|codex)\s+(-p|--print|exec)\b",
    re.MULTILINE,
)
SHELL_FILES = re.compile(
    r"(\.sh|Dockerfile[^/]*|\.Dockerfile|entrypoint[^/]*)$|(^|/)infra/systemd/"
)


def is_text(path: Path) -> bool:
    data = path.read_bytes()[:8192]
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def scanned_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode()
    result: list[str] = []
    for path in filter(None, listed.split("\0")):
        if path == THIS or path.startswith(EXCLUDED) or Path(path).suffix in PROSE:
            continue
        in_scope = "/" not in path or path.startswith(SCANNED_DIRECTORIES)
        if in_scope and (ROOT / path).is_file() and is_text(ROOT / path):
            result.append(path)
    return result


def findings(path: str, text: str) -> list[str]:
    """Every rule's matches in one file, as ``path:line: kind: match``."""
    found: list[tuple[int, str, str]] = []
    for kind, pattern in PATTERNS:
        found.extend((match.start(), kind, match.group(0)) for match in pattern.finditer(text))
    if DEPENDENCY_FILES.search(path):
        found.extend(
            (match.start(), ENGINE, match.group(0).strip("\"' /"))
            for match in HARNESS_DEPENDENCY.finditer(text)
        )
    for start in PROCESS_START.finditer(text):
        window = text[start.end() : start.end() + 300]
        engine = ENGINE_COMMAND.search(window)
        if engine:
            found.append((start.start(), ENGINE, start.group(0) + window[: engine.end()]))
    if SHELL_FILES.search(path) or text.startswith("#!"):
        found.extend(
            (match.start(), ENGINE, match.group(0)) for match in SHELL_ENGINE.finditer(text)
        )
    return [
        f"{path}:{text.count(chr(10), 0, offset) + 1}: {kind}: {match!r}"
        for offset, kind, match in sorted(found)
    ]


def test_the_scan_covers_lonoras_code_and_deployment() -> None:
    files = set(scanned_files())
    for expected in (
        "packages/adapters/src/lonora_adapters/models/anthropic.py",
        "packages/providers/src/lonora_providers/router.py",
        "apps/web/package.json",
        "apps/mobile/package.json",
        "pyproject.toml",
        "pnpm-lock.yaml",
        "Dockerfile",
        "docker-compose.yml",
        "entrypoint.sh",
        # Deployment files without a code suffix (R-SEC M3).
        "infra/analysis/analytics.Dockerfile",
        "infra/compose/Caddyfile.prod",
        "scripts/install.ps1",
    ):
        assert expected in files, expected
    assert any(path.startswith("infra/systemd/") for path in files)
    assert not any(path.endswith(".md") for path in files)
    assert len(files) > 1000


def caught(kind: str, sample: str, path: str = "packages/core/src/lonora_core/x.py") -> bool:
    return any(f": {kind}: " in line for line in findings(path, sample))


@pytest.mark.parametrize(
    ("kind", "sample", "path"),
    [
        (LOGIN, 'TOKEN = "sk-ant-oat01-abc"', None),
        (LOGIN, '"anthropic-beta": "oauth-2025-04-20"', None),
        (LOGIN, '"anthropic-beta": "claude-code-20250219"', None),
        (LOGIN, "client = Anthropic(auth_token=token)", None),
        (LOGIN, 'os.environ["ANTHROPIC_AUTH_TOKEN"]', None),
        (LOGIN, 'Path.home() / ".claude/.credentials.json"', None),
        (LOGIN, 'data["claudeAiOauth"]["accessToken"]', None),
        (LOGIN, 'security find-generic-password -s "Claude Code-credentials"', None),
        (LOGIN, 'Path.home() / ".codex/auth.json"', None),
        (LOGIN, 'Path.home() / ".claude" / ".credentials.json"', None),
        (LOGIN, '"https://platform.claude.com/v1/oauth/token"', None),
        (LOGIN, '"https://claude.com/cai/oauth/authorize"', None),
        (LOGIN, '"https://api.anthropic.com/api/oauth/claude_cli/create_api_key"', None),
        (LOGIN, "url = 'https://chatgpt.com/backend-api/codex'", None),
        (LOGIN, "run('claude setup-token')", None),
        (CLIENT_ID, 'CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"', None),
        (PRIVATE, 'BASE = "https://chatgpt.example/backend-api/codex"', None),
        (ENGINE, "from claude_agent_sdk import query", None),
        (ENGINE, 'import { query } from "@anthropic-ai/claude-agent-sdk";', None),
        (ENGINE, '"@anthropic-ai/claude-agent-sdk": "^0.1.0"', "apps/web/package.json"),
        (ENGINE, 'dependencies = ["langgraph>=0.2"]', "packages/core/pyproject.toml"),
        (ENGINE, 'subprocess.run(["claude", "-p", prompt])', None),
        (ENGINE, 'ENGINE = "claude"\nsubprocess.run([ENGINE, "-p", prompt])', None),
        (ENGINE, "const bin = '/usr/local/bin/codex';", "apps/web/src/x.ts"),
        (ENGINE, 'subprocess.run(f"claude -p {prompt}", shell=True)', None),
        (ENGINE, 'subprocess.Popen(["/usr/local/bin/claude", "--print", prompt])', None),
        (ENGINE, "await asyncio.create_subprocess_exec('codex', 'exec', task)", None),
        (ENGINE, "execSync(`claude -p ${prompt}`)", "apps/web/src/x.ts"),
        (ENGINE, 'exec claude --print "$PROMPT"', "infra/compose/run.sh"),
        (ENGINE, 'out=$(claude -p "$PROMPT")', "scripts/run-engine"),
        (ENGINE, 'ExecStart=/usr/local/bin/claude -p "run"', "infra/systemd/x.service"),
        (ENGINE, "claude-agent-sdk==0.1.0", "infra/analysis/analytics.requirements.lock"),
    ],
)
def test_each_rule_catches_what_it_names(kind: str, sample: str, path: str | None) -> None:
    if path == "scripts/run-engine":
        sample = "#!/usr/bin/env bash\n" + sample
    assert caught(kind, sample, *(() if path is None else (path,)))


@pytest.mark.parametrize(
    ("sample", "path"),
    [
        ('model = "gpt-5-codex"', None),  # a model id served through the public API
        ('model = "claude-sonnet-4-5"', None),
        ("https://api.anthropic.com/v1/messages", None),
        ("authorization_url(endpoint, client_id)", None),  # the generic MCP OAuth helper
        ("see https://chatgpt.com/ for the consumer app", None),
        ("# langgraph is another harness Lonora does not use", None),
        # Workspace tooling an agent may install and check (12.2, 7.1).
        ('subprocess.run(["claude", "--version"])', None),
        ("RUN npm i -g @anthropic-ai/claude-code", "infra/workspace/Dockerfile"),
        ('"@anthropic-ai/claude-code"', "infra/workspace/tools.json"),
        ('route = "/auth/setup-token"', None),
        ('provider = "anthropic"', None),
        ('family = "claude-sonnet-4-5"', None),
    ],
)
def test_ordinary_use_and_workspace_tooling_are_not_flagged(sample: str, path: str | None) -> None:
    assert not findings(path or "packages/core/src/lonora_core/x.py", sample)


def test_lonoras_code_has_no_subscription_login_private_endpoint_or_other_engine() -> None:
    found: list[str] = []
    for path in scanned_files():
        found.extend(findings(path, (ROOT / path).read_text(encoding="utf-8", errors="replace")))
    assert not found, "\n".join(found)


def test_every_model_adapter_calls_a_public_api_host() -> None:
    hosts = {urlsplit(url).hostname for url in PROVIDER_URLS.values()}
    assert hosts == PUBLIC_MODEL_HOSTS
    for provider, adapter in PROVIDERS.items():
        if provider == "openai_compatible":
            continue  # the owner's own base URL, checked when it is configured
        instance = adapter("fixture-not-a-real-key")
        assert isinstance(instance, BaseModelAdapter), provider
        assert urlsplit(instance.base_url).hostname in PUBLIC_MODEL_HOSTS, provider
        assert urlsplit(instance.base_url).scheme == "https", provider


def test_every_model_host_in_the_adapters_is_public() -> None:
    adapters = ROOT / "packages/adapters/src/lonora_adapters"
    for path in [*adapters.glob("models/*.py"), *adapters.glob("voice/*.py")]:
        for host in re.findall(r"(?:https|wss)://([a-z0-9.-]+)", path.read_text()):
            assert host in PUBLIC_MODEL_HOSTS, f"{path.relative_to(ROOT)}: {host}"
