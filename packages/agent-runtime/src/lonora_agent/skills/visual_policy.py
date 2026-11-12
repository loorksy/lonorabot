"""Stable, bounded response vocabulary; presentation remains the existing model's choice."""

import os
import re
from functools import lru_cache
from pathlib import Path

from lonora_core.user_error import LonoraError

from .loader import resources_root

VISUAL_MARKER = "<lonora_native_visual_response>"
VISUAL_END = "</lonora_native_visual_response>"
MAX_VISUAL_GUIDANCE_CHARS = 6500
# The v2 generative-UI block (GENUI_PLAN §9.5): decision guidance, rules, the generated
# vocabulary and the worked programs. The default (mandate 10.1.3), since web and mobile
# render the same component set; ``LONORA_GENUI_V2=0`` keeps the v1 block until the setting
# is deleted at the end of phase 2.
MAX_GENUI_GUIDANCE_CHARS = 18000


def genui_v2_enabled() -> bool:
    return os.environ.get("LONORA_GENUI_V2", "").strip().lower() not in {"0", "false", "off", "no"}


def genui_v2_variant() -> str:
    """The answer-shape teaching: P (the plan's) or O (Open Intelligent UI's, adapted).
    The decision evaluation chooses; LONORA_GENUI_PROMPT overrides it for an A/B run."""
    value = os.environ.get("LONORA_GENUI_PROMPT", "P").strip().upper()
    return value if value in {"P", "O"} else "P"


@lru_cache(maxsize=8)
def _read_v2(path: Path, modified: int, variant: str) -> str:
    del modified, variant
    from ..genui_vocabulary import genui_vocabulary

    teaching = (path.parent / f"genui_v2_teaching_{genui_v2_variant().lower()}.md").read_text()
    # Authoring comments (attribution, what was dropped) never reach the model.
    teaching = re.sub(r"<!--.*?-->\s*", "", teaching, flags=re.S).strip()
    text = (
        path.read_text()
        .strip()
        .replace("{teaching}", teaching)
        .replace("{vocabulary}", genui_vocabulary())
    )
    if (
        not text.startswith(VISUAL_MARKER)
        or not text.endswith(VISUAL_END)
        or len(text) > MAX_GENUI_GUIDANCE_CHARS
    ):
        raise LonoraError("visual_policy_invalid", 500)
    return text


def genui_v2_policy() -> str:
    path = resources_root() / "prompts" / "genui_v2.md"
    try:
        return _read_v2(path, path.stat().st_mtime_ns, genui_v2_variant())
    except OSError:
        raise LonoraError("visual_policy_invalid", 500) from None


@lru_cache(maxsize=4)
def _read(path: Path, modified: int) -> str:
    del modified
    text = path.read_text().strip()
    if (
        not text.startswith(VISUAL_MARKER)
        or not text.endswith(VISUAL_END)
        or len(text) > MAX_VISUAL_GUIDANCE_CHARS
    ):
        raise LonoraError("visual_policy_invalid", 500)
    return text


def native_visual_policy() -> str:
    if genui_v2_enabled():
        return genui_v2_policy()
    path = resources_root() / "prompts" / "native_visual_response.md"
    try:
        return _read(path, path.stat().st_mtime_ns)
    except OSError:
        raise LonoraError("visual_policy_invalid", 500) from None


def refresh_visual_policy(content: str) -> str:
    """Refresh old checkpoints in a request copy; never modify their canonical history."""
    if VISUAL_MARKER in content:
        return re.sub(
            re.escape(VISUAL_MARKER) + ".*?" + re.escape(VISUAL_END),
            lambda _: native_visual_policy(),
            content,
            count=1,
            flags=re.S,
        )
    end = "</lonora_operating_policy>"
    split = content.index(end) + len(end)
    return content[:split] + "\n\n" + native_visual_policy() + content[split:]
