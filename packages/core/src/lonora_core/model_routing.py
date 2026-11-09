import re

from lonora_contracts.model_routing import (
    TEXT_CAPABILITIES,
    Capability,
    ModelSelection,
    RoutingPolicy,
)

from .user_error import LonoraError


def select_model(policy: RoutingPolicy, capability: Capability) -> ModelSelection:
    audio = capability in {Capability.STT, Capability.TTS, Capability.REALTIME_VOICE}
    selected = policy.routes.get(capability) if policy.mode == "custom" or audio else policy.unified
    if selected is None and capability in {
        Capability.CONVERSATION,
        Capability.REASONING,
        Capability.RESEARCH,
        Capability.BACKGROUND,
    }:
        selected = policy.unified
    if selected is None:
        raise LonoraError("model_not_configured", 409)
    return selected


def text_routes(policy: RoutingPolicy) -> list[ModelSelection]:
    """The owner's global models for text work, in capability order, de-duplicated."""
    chosen: list[ModelSelection] = []
    for capability in TEXT_CAPABILITIES:
        try:
            selection = select_model(policy, capability)
        except LonoraError:
            continue
        if selection not in chosen:
            chosen.append(selection)
    return chosen


# Words of a model's id or catalog name: letter runs and digit runs ("gpt-4o" -> gpt, 4, o).
_MODEL_WORDS = re.compile(r"[a-z]+|[0-9]+")
# Words many model names share, or vendor names: they name no particular model.
GENERIC_MODEL_WORDS = frozenset(
    {
        "ai", "air", "and", "anthropic", "base", "beta", "chat", "code", "coder", "exp",
        "experimental", "fast", "flash", "for", "free", "google", "high", "instruct", "large",
        "latest", "lite", "low", "max", "medium", "meta", "mini", "mistralai", "model",
        "models", "nano", "new", "online", "openai", "openrouter", "plus", "preview", "pro",
        "reasoning", "search", "small", "the", "think", "thinking", "turbo", "vision", "with",
        "xai", "zai",
    }
)  # fmt: skip


def model_words(text: str) -> list[str]:
    return _MODEL_WORDS.findall(text.casefold())


def _contains(words: list[str], part: list[str]) -> bool:
    size = len(part)
    return size > 0 and any(words[i : i + size] == part for i in range(len(words) - size + 1))


def names_model(text: str, selection: ModelSelection, name: str | None) -> bool:
    """Whether the owner's words name this model: its id or catalog name ("GPT-4o",
    "claude-opus-4-1"), or a distinctive word of either ("Opus", "Sonnet")."""
    said = model_words(text)
    labels = [model_words(selection.model), *([model_words(name)] if name else [])]
    if any(_contains(said, label) for label in labels):
        return True
    distinctive = {
        word
        for label in labels
        for word in label
        if len(word) >= 3 and word.isalpha() and word not in GENERIC_MODEL_WORDS
    }
    return not distinctive.isdisjoint(said)


def model_match_score(query: str, provider: str, model: str, name: str) -> int:
    """How many words of a model query a catalog entry shares; 0 unless a word with
    letters matches (a bare version number names no model)."""
    hits = set(model_words(query)) & set(model_words(" ".join((provider, model, name))))
    return len(hits) if any(word.isalpha() and len(word) >= 2 for word in hits) else 0
