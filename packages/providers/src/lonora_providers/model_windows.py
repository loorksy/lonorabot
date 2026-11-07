"""Conservative context windows for model families whose catalog omits them.

Provider catalogs are preferred (OpenRouter reports ``context_length``); the
direct Anthropic, OpenAI, DeepSeek and Z.ai model listings do not. Values are
deliberately conservative lower bounds for the family, so an estimate never
admits more than the provider accepts: a too-small window only compacts earlier.
GPT-5 lists its input limit, not the combined window.

The longest-prefix family match follows Hermes Agent ``agent/model_metadata.py``
(``DEFAULT_CONTEXT_LENGTHS`` with ``_longest_key_match``), source
https://github.com/NousResearch/hermes-agent at revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a, MIT License, Copyright (c) 2025 Nous
Research; see THIRD_PARTY_NOTICES.md. The table itself is Lonora's own.
"""

FAMILY_SOURCE = "lonora_model_family_table_v1"

_FAMILIES: dict[str, int] = {
    "claude": 200_000,
    "claude-2": 100_000,
    "claude-instant": 100_000,
    "gpt-3.5-turbo": 16_385,
    "gpt-4": 8_192,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "gpt-4.1": 1_000_000,
    "gpt-5": 272_000,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o1-preview": 128_000,
    "o3": 200_000,
    "o4-mini": 200_000,
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "glm-4.5": 128_000,
    "glm-4.6": 200_000,
    "glm-4.7": 200_000,
    "glm-5": 200_000,
}


def family_window(model: str) -> int | None:
    """Longest matching family prefix of the bare model id, or ``None``."""
    name = model.strip().lower().rsplit("/", 1)[-1]
    matches = [key for key in _FAMILIES if name.startswith(key)]
    return _FAMILIES[max(matches, key=len)] if matches else None
