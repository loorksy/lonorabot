"""What the model reads of a failed tool result.

The Run record keeps the whole envelope (``code``, ``recovery``): recovery, the gates,
the scorer and the logs read it. The model reads the same failure in words. ``code``
becomes ``reason`` with its words spelled out, and the recovery labels likewise, so a
reply cannot carry a machine code the model never saw. Tool names stay exact (the
model calls them), and a result that did not fail is not touched.
"""

import json
import re
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage

_LABEL = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
_FAILED = frozenset({"failed", "rejected"})
_FAILURE = '"ok": false'


def _words(value: Any) -> Any:
    return value.replace("_", " ") if isinstance(value, str) and _LABEL.fullmatch(value) else value


def _failure(result: dict[str, Any]) -> dict[str, Any]:
    view = dict(result)
    if "code" in view:
        view["reason"] = _words(view.pop("code"))
    recovery = view.get("recovery")
    if isinstance(recovery, dict):
        view["recovery"] = {
            key: _words(value) if key in {"category", "next_action"} else value
            for key, value in cast(dict[str, Any], recovery).items()
        }
    results = view.get("results")
    if isinstance(results, list):
        view["results"] = [
            _failure(cast(dict[str, Any], item))
            if isinstance(item, dict) and cast(dict[str, Any], item).get("status") in _FAILED
            else item
            for item in cast(list[Any], results)
        ]
    return view


def failure_view(messages: list[ModelMessage]) -> list[ModelMessage]:
    """The request's messages with every failed tool result put in words."""
    viewed: list[ModelMessage] = []
    for message in messages:
        if message.role == "tool" and _FAILURE in message.content:
            try:
                result = json.loads(message.content)
            except ValueError:
                result = None
            if isinstance(result, dict) and cast(dict[str, Any], result).get("ok") is False:
                message = message.model_copy(
                    update={
                        "content": json.dumps(
                            _failure(cast(dict[str, Any], result)), ensure_ascii=False
                        )
                    }
                )
        viewed.append(message)
    return viewed
