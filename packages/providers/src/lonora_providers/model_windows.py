"""Conservative context windows for model families whose catalog omits them.

Provider catalogs are preferred (OpenRouter reports ``context_length``); the
direct Anthropic, OpenAI, DeepSeek and Z.ai model listings do not. Values are
deliberately conservative for the family they name. A family key matches only
at an id boundary (end of id, ``-``, ``:`` or ``@``), so ``gpt-4`` does not
claim ``gpt-4.5-preview`` and ``glm-4.5`` does not claim the ``glm-4.5v``
vision model; an id the table does not cover stays unknown and uses the
policy's ``maximum_input_tokens``. A wrong entry still mis-sizes requests, so the
table must follow provider documentation. GPT-5 lists its input limit, not the
combined window. The output table is used the same way: a documented family
maximum lets the router request more than the policy's unknown-model cap.

The longest-prefix family match follows Hermes Agent ``agent/model_metadata.py``
(``DEFAULT_CONTEXT_LENGTHS`` with ``_longest_key_match``), source
https://github.com/NousResearch/hermes-agent at revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a, MIT License, Copyright (c) 2025 Nous
Research; see THIRD_PARTY_NOTICES.md. The boundary rule and the table itself
are Lonora's own.
"""

FAMILY_SOURCE = "lonora_model_family_table_v2"
OUTPUT_SOURCE = "lonora_model_output_table_v1"
# What may follow a family key in a longer id: snapshot dates, tags, variants.
_BOUNDARIES = frozenset("-:@")

_FAMILIES: dict[str, int] = {
    "claude": 200_000,
    "claude-2": 100_000,
    "claude-instant": 100_000,
    "gpt-3.5-turbo": 16_385,
    "gpt-3.5-turbo-instruct": 4_096,
    "gpt-4": 8_192,
    "gpt-4-32k": 32_768,
    # GPT-4 Turbo previews share the gpt-4 prefix but have 128k windows.
    "gpt-4-0125-preview": 128_000,
    "gpt-4-1106-preview": 128_000,
    "gpt-4-vision-preview": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "gpt-4.1": 1_000_000,
    "gpt-4.5": 128_000,
    "gpt-5": 272_000,
    "gpt-5-chat": 128_000,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o1-preview": 128_000,
    "o3": 200_000,
    "o4-mini": 200_000,
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "glm-4.5": 128_000,
    "glm-4.5v": 64_000,
    "glm-4.6": 200_000,
    "glm-4.6v": 128_000,
    "glm-4.7": 200_000,
    "glm-5": 200_000,
}


# Documented maximum output tokens per family, used only when the catalog does
# not report one. Unknown ids stay unknown (the caller applies its own cap) and
# a provider that rejects a budget states its limit, which the router learns.
_OUTPUTS: dict[str, int] = {
    "claude": 8_192,
    "claude-3": 4_096,
    "claude-3-5": 8_192,
    "claude-3-7": 64_000,
    "claude-sonnet-4": 64_000,
    "claude-opus-4": 32_000,
    "claude-opus-4-5": 64_000,
    "claude-sonnet-4-5": 64_000,
    "claude-haiku-4-5": 64_000,
    "claude-opus-4-6": 128_000,
    "claude-sonnet-4-6": 128_000,
    "claude-opus-4-7": 128_000,
    "claude-opus-4-8": 128_000,
    "claude-opus-5": 128_000,
    "claude-sonnet-5": 128_000,
    "claude-haiku-5": 128_000,
    "claude-fable-5": 128_000,
    "gpt-3.5-turbo": 4_096,
    "gpt-4": 8_192,
    "gpt-4-0125-preview": 4_096,
    "gpt-4-1106-preview": 4_096,
    "gpt-4-vision-preview": 4_096,
    "gpt-4-turbo": 4_096,
    "gpt-4o": 16_384,
    "gpt-4.1": 32_768,
    "gpt-4.5": 16_384,
    "gpt-5": 128_000,
    "gpt-5-chat": 16_384,
    "o1": 100_000,
    "o1-mini": 65_536,
    "o1-preview": 32_768,
    "o3": 100_000,
    "o4-mini": 100_000,
    "deepseek-chat": 8_192,
    "deepseek-reasoner": 64_000,
}


def _matches(name: str, key: str) -> bool:
    return name == key or (name.startswith(key) and name[len(key)] in _BOUNDARIES)


def family_window(model: str) -> int | None:
    """Longest family key matching the bare model id at a boundary, or ``None``."""
    name = model.strip().lower().rsplit("/", 1)[-1]
    matches = [key for key in _FAMILIES if _matches(name, key)]
    return _FAMILIES[max(matches, key=len)] if matches else None


def family_output(model: str) -> int | None:
    """Longest family key's documented maximum output, or ``None``."""
    name = model.strip().lower().rsplit("/", 1)[-1]
    matches = [key for key in _OUTPUTS if _matches(name, key)]
    return _OUTPUTS[max(matches, key=len)] if matches else None
