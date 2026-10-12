from dataclasses import dataclass

from lonora_contracts.usage import TokenUsage


@dataclass(frozen=True)
class UsageRecord:
    run_id: str
    provider: str
    model: str
    tokens: TokenUsage
