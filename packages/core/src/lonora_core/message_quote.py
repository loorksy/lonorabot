def quote(content: str, limit: int = 1600) -> str:
    return "\n".join("> " + line for line in content[:limit].splitlines())
