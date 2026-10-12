def normalize_memory(content: str) -> str:
    return content.replace("\r\n", "\n").strip() + ("\n" if content.strip() else "")


def memory_context(content: str) -> str:
    return "<persistent_memory>\n" + content + "\n</persistent_memory>" if content.strip() else ""
