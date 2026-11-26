"""List prices per provider/model, used to show usage cost (owner decisions D4, Q22).

Prices are USD per million tokens for uncached input, cached (cache-read) input and
output, as Lonora's model list states them (``model_list``, VISION 12.4): every provider's
listed models are priced from the list, ``PRICES_AS_OF`` names the package it was imported
from. Cost is a view of what a request cost at list price; it never limits anything. A
model the list does not hold, or one listed without a price (all zero), has no cost
(``None``): a price is never guessed and never taken as free. A listed model without a
cache-read price prices a request with cached tokens as unknown too. A variant (``-mini``,
``-pro``, a new minor version) is a different model with its own entry. Only Anthropic's
dated ids (``-20250929``, ``@20250929``), which its price table names as the same model,
are priced as the listed model when the list does not hold them; any other provider's
unlisted snapshot is unpriced. The owner's own endpoint is never priced.

Not modelled: cache writes (the adapters do not record ``cache_creation_input_tokens``),
long-context premium tiers (above a model's long-context threshold), batch and priority
tiers, fast mode. Each of these makes the shown cost a lower bound for the affected
requests.
"""

import re
from dataclasses import dataclass
from typing import cast

from .model_list import list_package, listed_entry

PRICES_AS_OF = list_package()

# Whether a provider's reported input tokens already include the cached ones. Anthropic
# reports ``input_tokens`` without ``cache_read_input_tokens``; the OpenAI-compatible
# APIs report ``prompt_tokens`` with ``prompt_tokens_details.cached_tokens`` inside it.
_INPUT_EXCLUDES_CACHED = frozenset({"anthropic"})


@dataclass(frozen=True)
class ModelPrice:
    input: float
    # ``None`` when the list states no cache-read price (zero): cached tokens are unpriced.
    cached_input: float | None
    output: float


_SNAPSHOT = re.compile(r"[-@]\d{8}$")
# Providers whose price table names a dated id as the same model.
_SNAPSHOT_IS_MODEL = frozenset({"anthropic"})


def _listed_price(provider: str, model: str) -> ModelPrice | None:
    entry = listed_entry(provider, model)
    if entry is None:
        return None
    cost = cast(dict[str, float], entry["cost"])
    if not any(cost.values()):
        return None
    return ModelPrice(cost["input"], cost["cache_read"] or None, cost["output"])


def model_price(provider: str, model: str) -> ModelPrice | None:
    """The list price of a listed model or its dated snapshot, else ``None``."""
    key, name = provider.strip().lower(), model.strip().lower()
    if listed_entry(key, name) is not None:
        return _listed_price(key, name)
    return _listed_price(key, _SNAPSHOT.sub("", name)) if key in _SNAPSHOT_IS_MODEL else None


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
    cached rate, whether or not the provider includes them in its input count. Cached
    tokens without a cached rate leave the request unpriced, never free."""
    price = model_price(provider, model)
    if price is None:
        return None
    prompt = prompt_tokens(provider, input_tokens, cached_tokens)
    cached = min(cached_tokens, prompt)
    if cached and price.cached_input is None:
        return None
    return (
        (prompt - cached) * price.input
        + cached * (price.cached_input or 0.0)
        + output_tokens * price.output
    ) / 1_000_000
