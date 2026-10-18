from dataclasses import dataclass, field
from typing import Any

from lonora_contracts.usage import TokenUsage


@dataclass(frozen=True)
class UsageRecord:
    run_id: str
    provider: str
    model: str
    tokens: TokenUsage
    context_budget: dict[str, Any] = field(default_factory=dict[str, Any])
