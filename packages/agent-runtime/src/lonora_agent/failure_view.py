"""What the model reads of a tool result that did not simply succeed.

The Run record keeps the whole envelope (``code``, ``recovery``): recovery, the gates,
the scorer and the logs read it. The model reads the same result in words. ``code``
becomes ``reason`` with its words spelled out, and the recovery labels likewise, so a
reply cannot carry a machine code the model never saw. That holds for a failure, for
an outcome that is not yet known and for a result that only notes why nothing was done.
Tool names stay exact (the model calls them), and a result with neither is not touched.
"""

import json
import re
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage

_LABEL = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
_MARKED = ('"code"', '"recovery"')


def _words(value: Any) -> Any:
    return value.replace("_", " ") if isinstance(value, str) and _LABEL.fullmatch(value) else value


def _in_words(result: dict[str, Any]) -> dict[str, Any]:
    view = dict(result)
    code = view.get("code")
    # A failure's code is always ours; elsewhere only a machine label is one.
    if isinstance(code, str) and (view.get("ok") is False or _LABEL.fullmatch(code)):
        del view["code"]
        # A reason the result already gives is kept beside the code's words.
        own = view.get("reason")
        view["reason"] = (
            f"{_words(code)}: {_words(own)}" if isinstance(own, str) and own else _words(code)
        )
    recovery = view.get("recovery")
    if isinstance(recovery, dict):
        view["recovery"] = {
            key: _words(value) if key in {"category", "next_action"} else value
            for key, value in cast(dict[str, Any], recovery).items()
        }
    results = view.get("results")
    if isinstance(results, list):
        view["results"] = [
            _in_words(cast(dict[str, Any], item)) if isinstance(item, dict) else item
            for item in cast(list[Any], results)
        ]
    return view


def failure_view(messages: list[ModelMessage]) -> list[ModelMessage]:
    """The request's messages with every tool result's machine labels put in words."""
    viewed: list[ModelMessage] = []
    for message in messages:
        if message.role == "tool" and any(mark in message.content for mark in _MARKED):
            try:
                result = json.loads(message.content)
            except ValueError:
                result = None
            if isinstance(result, dict):
                view = _in_words(cast(dict[str, Any], result))
                if view != result:
                    message = message.model_copy(
                        update={"content": json.dumps(view, ensure_ascii=False)}
                    )
        viewed.append(message)
    return viewed
