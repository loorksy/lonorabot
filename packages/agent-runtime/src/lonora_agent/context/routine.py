from lonora_db.schema import RunRow


def wake_context(run: RunRow) -> str:
    if run.trigger in {"user", "group"} and not run.prompt:
        return ""
    return "<wake trigger='" + run.trigger + "'>\n" + run.prompt + "\n</wake>"
