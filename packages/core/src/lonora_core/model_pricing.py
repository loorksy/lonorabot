"""Public list prices per provider/model, used to show usage cost (owner decisions D4, Q22).

Prices are USD per million tokens for uncached input, cached (cache-read) input and
output, standard tier. Cost is a view of what a request cost at list price; it never
limits anything. A model the table does not name has no cost (``None``): a price is
never guessed, and a variant (``-mini``, ``-pro``, a new minor version) is a different
model with its own row. Only a dated snapshot of a listed model (``-20250929``,
``-2024-08-06``, ``@20250929``) is priced as that model.

Recorded on ``PRICES_AS_OF``. Anthropic rows follow Anthropic's published model pricing
(table dated 2026-11-03). OpenAI, DeepSeek and Z.ai rows are the providers' published
list prices as last confirmed (their pricing pages could not be re-read on the
recording date); update them when a provider changes its prices. OpenRouter re-sells
other providers' models under its own ids and is not priced here.

Not modelled: cache writes (the adapters do not record ``cache_creation_input_tokens``),
long-context premium tiers (Claude Haiku 5.5 above 100K prompt tokens, Sonnet 4.x above
200K), batch and priority tiers, fast mode. Each of these makes the shown cost a lower
bound for the affected requests.
"""

import re
from dataclasses import dataclass

PRICES_AS_OF = "2026-11-10"

# Whether a provider's reported input tokens already include the cached ones. Anthropic
# reports ``input_tokens`` without ``cache_read_input_tokens``; the OpenAI-compatible
# APIs report ``prompt_tokens`` with ``prompt_tokens_details.cached_tokens`` inside it.
_INPUT_EXCLUDES_CACHED = frozenset({"anthropic"})


@dataclass(frozen=True)
class ModelPrice:
    input: float
    cached_input: float
    output: float


def _p(input: float, cached_input: float, output: float) -> ModelPrice:
    return ModelPrice(input, cached_input, output)


_PRICES: dict[str, dict[str, ModelPrice]] = {
    "anthropic": {
        "claude-fable-5-2": _p(8.00, 0.20, 40.00),
        "claude-mythos-5-2": _p(8.00, 0.20, 40.00),
        "claude-fable-5-1": _p(10.00, 0.25, 50.00),
        "claude-mythos-5-1": _p(10.00, 0.25, 50.00),
        "claude-fable-5": _p(10.00, 1.00, 50.00),
        "claude-mythos-5": _p(10.00, 1.00, 50.00),
        "claude-opus-5-5": _p(4.00, 0.20, 20.00),
        "claude-opus-5": _p(5.00, 0.50, 25.00),
        "claude-opus-4-8": _p(5.00, 0.50, 25.00),
        "claude-opus-4-7": _p(5.00, 0.50, 25.00),
        "claude-opus-4-6": _p(5.00, 0.50, 25.00),
        "claude-opus-4-5": _p(5.00, 0.50, 25.00),
        "claude-opus-4-1": _p(15.00, 1.50, 75.00),
        "claude-opus-4": _p(15.00, 1.50, 75.00),
        "claude-sonnet-5-5": _p(2.00, 0.10, 10.00),
        "claude-sonnet-5": _p(2.00, 0.20, 10.00),
        "claude-sonnet-4-6": _p(3.00, 0.30, 15.00),
        "claude-sonnet-4-5": _p(3.00, 0.30, 15.00),
        "claude-sonnet-4": _p(3.00, 0.30, 15.00),
        "claude-3-7-sonnet": _p(3.00, 0.30, 15.00),
        "claude-haiku-5-5": _p(0.10, 0.01, 0.50),
        "claude-haiku-4-5": _p(1.00, 0.10, 5.00),
        "claude-3-5-haiku": _p(0.80, 0.08, 4.00),
    },
    "openai": {
        "gpt-5": _p(1.25, 0.125, 10.00),
        "gpt-5-chat-latest": _p(1.25, 0.125, 10.00),
        "gpt-5-mini": _p(0.25, 0.025, 2.00),
        "gpt-5-nano": _p(0.05, 0.005, 0.40),
        "gpt-4.1": _p(2.00, 0.50, 8.00),
        "gpt-4.1-mini": _p(0.40, 0.10, 1.60),
        "gpt-4.1-nano": _p(0.10, 0.025, 0.40),
        "gpt-4o": _p(2.50, 1.25, 10.00),
        "gpt-4o-mini": _p(0.15, 0.075, 0.60),
        "o3": _p(2.00, 0.50, 8.00),
        "o4-mini": _p(1.10, 0.275, 4.40),
        "o3-mini": _p(1.10, 0.55, 4.40),
        "o1": _p(15.00, 7.50, 60.00),
    },
    "deepseek": {
        "deepseek-chat": _p(0.28, 0.028, 0.42),
        "deepseek-reasoner": _p(0.28, 0.028, 0.42),
    },
    "zai": {
        "glm-4.6": _p(0.60, 0.11, 2.20),
        "glm-4.5": _p(0.60, 0.11, 2.20),
        "glm-4.5-air": _p(0.20, 0.03, 1.10),
        "glm-4.5v": _p(0.60, 0.11, 1.80),
    },
}

_SNAPSHOT = re.compile(r"[-@](\d{8}|\d{4}-\d{2}-\d{2})$")


def model_price(provider: str, model: str) -> ModelPrice | None:
    """The list price of a listed model or its dated snapshot, else ``None``."""
    table = _PRICES.get(provider.strip().lower())
    if table is None:
        return None
    name = _SNAPSHOT.sub("", model.strip().lower())
    return table.get(name)


def prompt_tokens(provider: str, input_tokens: int, cached_tokens: int) -> int:
    """Every prompt token of a request, cached included, whatever the provider reports."""
    if provider.strip().lower() in _INPUT_EXCLUDES_CACHED:
        return input_tokens + cached_tokens
    return input_tokens


def usage_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int, cached_tokens: int
) -> float | None:
    """USD at list price: uncached input, cached input at the cached rate, and output.

    Token counts are as recorded (``TokenUsage``); cached tokens are counted once, at the
    cached rate, whether or not the provider includes them in its input count."""
    price = model_price(provider, model)
    if price is None:
        return None
    prompt = prompt_tokens(provider, input_tokens, cached_tokens)
    cached = min(cached_tokens, prompt)
    return (
        (prompt - cached) * price.input + cached * price.cached_input + output_tokens * price.output
    ) / 1_000_000
