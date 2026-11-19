"""The generative-UI block of the system prompt (lonora-ui v2, mandate 10.1.3): the answer
shape teaching, the rules, the vocabulary generated from the contract and the worked
examples. Presentation remains the model's choice."""

import re
from functools import lru_cache
from pathlib import Path

from lonora_core.user_error import LonoraError

from .loader import resources_root

VISUAL_MARKER = "<lonora_native_visual_response>"
VISUAL_END = "</lonora_native_visual_response>"
MAX_GENUI_GUIDANCE_CHARS = 18000


@lru_cache(maxsize=4)
def _read(path: Path, modified: int, teaching_modified: int) -> str:
    del modified, teaching_modified
    from ..genui_vocabulary import genui_vocabulary

    teaching = (path.parent / "genui_v2_teaching.md").read_text()
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


def native_visual_policy() -> str:
    path = resources_root() / "prompts" / "genui_v2.md"
    try:
        teaching = path.parent / "genui_v2_teaching.md"
        return _read(path, path.stat().st_mtime_ns, teaching.stat().st_mtime_ns)
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
