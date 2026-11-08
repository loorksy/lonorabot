"""What woke a Run, as first-party context in the system role.

Only prompts the server writes itself stay in the system role. A prompt that a
model or a person wrote (a subagent's task from its parent model, a peer request,
a Task or ticket title, a routine or watch prompt saved by an agent) may carry
injected text, so the system role names only the trigger: the builder delivers
that prompt as the user-role turn, where it is a request, never policy.
"""

from lonora_db.schema import RunRow

# Triggers whose run.prompt is fixed server text (lonora_trading, lonora_db).
SERVER_AUTHORED_TRIGGERS = frozenset({"goal", "broker_event", "follow_up", "activation"})


def wake_context(run: RunRow) -> str:
    if run.trigger == "peer" and run.model_metadata.get("peer_message_id"):
        return ""
    if run.trigger in {"user", "group"} and not run.prompt:
        return ""
    trigger = "".join(char for char in run.trigger if char.isalnum() or char == "_")
    if run.trigger not in SERVER_AUTHORED_TRIGGERS:
        return "<wake trigger='" + trigger + "' request='in_the_conversation_turn'/>"
    return "<wake trigger='" + trigger + "'>\n" + run.prompt + "\n</wake>"
