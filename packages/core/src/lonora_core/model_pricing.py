"""Public list prices per provider/model, used to show usage cost (owner decisions D4, Q22).

Prices are USD per million tokens for uncached input, cached (cache-read) input and
output, standard tier. Cost is a view of what a request cost at list price; it never
limits anything. A model the table does not name has no cost (``None``): a price is
never guessed, and a variant (``-mini``, ``-pro``, a new minor version) is a different
model with its own row. Only Anthropic's dated ids (``-20250929``, ``@20250929``), which its
price table names as the same model, are priced as the listed model; any other dated
snapshot is unpriced unless it has its own row.

Recorded on ``PRICES_AS_OF``: the rows follow Anthropic's published model pricing (table
dated 2026-11-03). OpenAI, DeepSeek, Z.ai and OpenRouter prices could not be verified on
the recording date, so their models are unpriced (cost ``None``, counted as
``unpriced_requests``) until verified rows are added.

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
}
_SNAPSHOT = re.compile(r"[-@]\d{8}$")
# Providers whose price table names a dated id as the same model.
_SNAPSHOT_IS_MODEL = frozenset({"anthropic"})


def model_price(provider: str, model: str) -> ModelPrice | None:
    """The list price of a listed model or its dated snapshot, else ``None``."""
    key = provider.strip().lower()
    table = _PRICES.get(key)
    if table is None:
        return None
    name = model.strip().lower()
    if name in table:
        return table[name]
    return table.get(_SNAPSHOT.sub("", name)) if key in _SNAPSHOT_IS_MODEL else None


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
