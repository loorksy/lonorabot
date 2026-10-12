from typing import Any

from lonora_contracts.usage import TokenUsage


def normalize_usage(value: dict[str, Any]) -> TokenUsage:
    return TokenUsage(
        input_tokens=max(0, int(value.get("input_tokens", value.get("prompt_tokens", 0)))),
        output_tokens=max(0, int(value.get("output_tokens", value.get("completion_tokens", 0)))),
        cached_tokens=max(0, int(value.get("cached_tokens", 0))),
    )
