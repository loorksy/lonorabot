"""Named profile views over one versioned MEMORY document, without a second store."""

import json
import re


def profile_documents(content: str) -> dict[str, str]:
    """Explicit headings only; never infer a preference from financial prose."""
    parts = re.split(r"(?m)^# (USER\.md|(?:memory/)?MEMORY\.md)[ \t]*\n", content)
    documents: dict[str, str] = {}
    legacy = parts[0].strip()
    if legacy:
        documents["memory/MEMORY.md"] = legacy
    for index in range(1, len(parts), 2):
        name = "USER.md" if parts[index] == "USER.md" else "memory/MEMORY.md"
        body = parts[index + 1].strip()
        if body:
            documents[name] = "\n\n".join(filter(None, [documents.get(name, ""), body]))
    return documents


def profile_context(content: str) -> str:
    documents = profile_documents(content)
    if not documents:
        return ""
    # JSON escaping keeps remembered markup inside a lower-trust evidence value.
    payload = json.dumps(documents, ensure_ascii=False).replace("<", "\\u003c")
    return "<persistent_memory>\n" + payload + "\n</persistent_memory>"
