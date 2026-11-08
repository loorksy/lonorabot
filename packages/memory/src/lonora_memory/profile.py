"""Named views of an Agent's own memory document and the owner's shared profile.

An Agent's memory row holds its private knowledge (``# MEMORY.md``, plus older
unsectioned text) and its operating notes (``# OPERATING.md``). What the owner says
about himself lives in the one owner profile every Agent reads (``ln_owner_profile``).
A ``# USER.md`` section that earlier releases kept inside an Agent row was merged
into that profile by migration 0039; it stays in the row but is no longer read from it.
"""

import json

# Explicit view headings only (the stored row format); never infer a preference from
# financial prose.
from lonora_db.memory import LEGACY_USER_VIEW, VIEW_HEADING, memory_view

MEMORY_VIEW = "memory/MEMORY.md"
OPERATING_VIEW = "OPERATING.md"


def view_name(heading: str) -> str:
    if heading in (LEGACY_USER_VIEW, OPERATING_VIEW):
        return heading
    return MEMORY_VIEW


def profile_documents(content: str) -> dict[str, str]:
    """Every explicit view of one document; unsectioned text is long-term memory."""
    parts = VIEW_HEADING.split(content)
    documents: dict[str, str] = {}
    legacy = parts[0].strip()
    if legacy:
        documents[MEMORY_VIEW] = legacy
    for index in range(1, len(parts), 2):
        name = view_name(parts[index])
        body = parts[index + 1].strip()
        if body:
            documents[name] = "\n\n".join(filter(None, [documents.get(name, ""), body]))
    return documents


def agent_memory_view(content: str) -> str:
    """The Agent's own document without retired ``# USER.md`` sections."""
    return memory_view(content)


def escaped_json(value: object) -> str:
    # JSON escaping keeps remembered markup inside a lower-trust evidence value.
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def profile_context(content: str) -> str:
    """The Agent's private knowledge views as escaped JSON (operating notes apart)."""
    documents = {
        name: body
        for name, body in profile_documents(content).items()
        if name not in (LEGACY_USER_VIEW, OPERATING_VIEW)
    }
    if not documents:
        return ""
    return "<persistent_memory>\n" + escaped_json(documents) + "\n</persistent_memory>"


def operating_notes(content: str) -> str:
    return profile_documents(content).get(OPERATING_VIEW, "")
