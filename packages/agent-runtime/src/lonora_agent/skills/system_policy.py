"""Bounded first-party policy, selected by actual operations, never keyword commands.

The full auditable manual is shipped once. Mandatory rules are always loaded;
only recent operation chapters enter a working request. Nothing grants authority.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from lonora_adapter_kit.types import ModelMessage, ToolDefinition
from lonora_core.user_error import LonoraError

from .loader import resources_root

MAX_CORE_CHARS = 16000
MAX_DOMAIN_CHARS = 14000
MAX_DOMAINS = 3
CORE_MARKER = "<lonora_operating_policy>"
DOMAIN_MARKER = "<lonora_domain_guidance>"


@dataclass(frozen=True)
class PolicyBundle:
    sections: dict[str, str]
    tool_policies: dict[str, str]
    digest: str
    examples: dict[str, list[str]]


@lru_cache(maxsize=4)
def _load(path: Path, mtime_ns: int, manifest_mtime_ns: int) -> PolicyBundle:
    del mtime_ns, manifest_mtime_ns  # Part of the development/cache identity.
    try:
        content = path.read_text()
        manifest = json.loads(path.with_name("manifest.json").read_text())
        digest = hashlib.sha256(content.encode()).hexdigest()
        if (
            len(content) > 1000000
            or manifest["version"] != 1
            or manifest["manual_sha256"] != digest
        ):
            raise ValueError("manual_manifest_mismatch")
        sections: dict[str, str] = {}
        for match in re.finditer(
            r"<!-- policy:([a-z_]+) -->\n(.*?)<!-- /policy -->", content, re.S
        ):
            name, body = match.groups()
            if name in sections or not body.strip():
                raise ValueError("duplicate_or_empty_policy")
            sections[name] = body.strip()
        if not {"core", "voice", "voice_surface"}.issubset(sections):
            raise ValueError("mandatory_policy_missing")
        if len(sections["core"]) > MAX_CORE_CHARS or len(sections["voice_surface"].encode()) > 800:
            raise ValueError("mandatory_policy_oversized")
        policies = cast(dict[str, str], manifest["tool_policies"])
        if not policies or any(v not in sections for v in policies.values()):
            raise ValueError("tool_policy_unknown")
        if any(
            len(sections[v]) > MAX_DOMAIN_CHARS // MAX_DOMAINS
            for v in policies.values()
            if v != "core"
        ):
            raise ValueError("domain_policy_oversized")
        examples: dict[str, list[str]] = {}
        for match in re.finditer(
            r"### Example \d+: ([a-z]+)\n\n(.*?)<!-- /example -->", content, re.S
        ):
            domain, body = match.groups()
            examples.setdefault(domain, []).append(
                "Hypothetical example, never current evidence:\n" + body.strip()
            )
        return PolicyBundle(sections, policies, digest, examples)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise LonoraError("operating_policy_invalid", 500) from None


def policy_bundle() -> PolicyBundle:
    path = resources_root() / "system" / "lonora.md"
    try:
        return _load(
            path, path.stat().st_mtime_ns, path.with_name("manifest.json").stat().st_mtime_ns
        )
    except OSError:
        raise LonoraError("operating_policy_invalid", 500) from None


def mandatory_policy() -> str:
    bundle = policy_bundle()
    samples = [bundle.examples["trading"][i] for i in (0, 2, 3)]
    body = bundle.sections["core"] + "\n\n" + "\n\n".join(samples)
    if len(body) > MAX_CORE_CHARS:
        raise LonoraError("operating_policy_invalid", 500)
    return CORE_MARKER + "\n" + body + "\n</lonora_operating_policy>"


def voice_surface_policy() -> str:
    return policy_bundle().sections["voice_surface"]


def validate_system_policy(known_tools: set[str]) -> None:
    if set(policy_bundle().tool_policies) != known_tools:
        raise LonoraError("operating_policy_tool_catalog_stale", 500)


def apply_operating_policy(
    messages: list[ModelMessage], tools: list[ToolDefinition]
) -> list[ModelMessage]:
    """Fresh request projection only; canonical history/checkpoints stay unchanged.

    Actual tool-call names select chapters. No owner-text matching, hidden intent
    classifier or extra paid model call. Complete exchanges remain indivisible.
    """
    bundle = policy_bundle()
    allowed = {tool.name for tool in tools}
    domains: list[str] = []
    for message in reversed(messages[-16:]):
        if message.role != "assistant":
            continue
        for call in reversed(message.tool_calls):
            name = bundle.tool_policies.get(call.name) if call.name in allowed else None
            if name and name != "core" and name not in domains:
                domains.append(name)
    # Stable ordering for equivalent sets keeps the reusable instruction prefix stable.
    chapters = [
        bundle.sections[name] + "\n\n" + "\n\n".join(bundle.examples.get(name, [])[:1])
        for name in sorted(domains[:MAX_DOMAINS])
    ]
    if sum(map(len, chapters)) > MAX_DOMAIN_CHARS:
        raise LonoraError("operating_policy_invalid", 500)
    result = list(messages)
    # Already checkpointed executions from an older release still get current rules.
    if not result or result[0].role != "system" or CORE_MARKER not in result[0].content:
        result.insert(0, ModelMessage(role="system", content=mandatory_policy()))
    if chapters:
        index = next(
            (i for i, message in enumerate(result) if message.role != "system"), len(result)
        )
        result.insert(
            index,
            ModelMessage(
                role="system",
                content=DOMAIN_MARKER
                + "\n"
                + "\n\n".join(chapters)
                + "\n</lonora_domain_guidance>",
            ),
        )
    return result
