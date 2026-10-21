def normalize_memory(content: str) -> str:
    return content.replace("\r\n", "\n").strip() + ("\n" if content.strip() else "")


def memory_context(content: str) -> str:
    from .profile import profile_context

    return profile_context(content)
