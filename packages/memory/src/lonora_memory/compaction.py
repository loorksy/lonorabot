def compact_document(content: str, maximum_chars: int = 24000) -> str:
    if len(content) <= maximum_chars:
        return content
    # An explicit bounded working copy; the durable MEMORY.md remains unchanged.
    paragraphs = content.split("\n\n")
    retained: list[str] = []
    remaining = maximum_chars
    for paragraph in paragraphs:
        if len(paragraph) + 2 > remaining:
            break
        retained.append(paragraph)
        remaining -= len(paragraph) + 2
    return "\n\n".join(retained)
