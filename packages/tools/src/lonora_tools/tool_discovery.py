"""Bounded catalog ranking adapted from Hermes Agent's tool_search_catalog.py.

Source: NousResearch/hermes-agent, revision
c78ca093aa4b6759c055c3ed2bfbe7f741cf0292. Adaptation uses Unicode tokens,
Lonora's existing typed definitions and exact native calls; no bridge or stemmer.

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import math
import re
import unicodedata
from collections import Counter

from lonora_adapter_kit.types import ToolDefinition

MAX_SEARCH_RESULTS = 5


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())


def search_definitions(
    definitions: list[ToolDefinition], query: str, limit: int = MAX_SEARCH_RESULTS
) -> list[str]:
    """Rank only the supplied permitted catalog; this is discovery, not routing."""
    query_tokens = set(tokens(query))
    limit = min(MAX_SEARCH_RESULTS, max(0, limit))
    if not query_tokens or not definitions or not limit:
        return []
    corpus = [
        tokens(
            " ".join((item.name, item.description, *item.parameters.get("properties", {}).keys()))
        )
        for item in definitions
    ]
    frequencies = Counter(token for document in corpus for token in set(document))
    average_length = sum(map(len, corpus)) / len(corpus)
    # A missing distinctive term must not produce unrelated tools merely because
    # generic verbs match. Exact registered names are always discoverable.
    gate = min(query_tokens, key=lambda token: (frequencies[token], token))
    answerable = {token for token in query_tokens if frequencies[token]}
    minimum_coverage = math.ceil(len(answerable) / 2) if len(answerable) >= 4 else 1
    ranked: list[tuple[float, str]] = []
    for definition, document in zip(definitions, corpus, strict=True):
        exact = query.strip().casefold() == definition.name.casefold()
        term_counts = Counter(document)
        if not exact and (
            not term_counts[gate]
            or sum(token in term_counts for token in answerable) < minimum_coverage
        ):
            continue
        score = 0.0
        for term in query_tokens:
            frequency, count = frequencies[term], term_counts[term]
            if frequency and count:
                inverse_frequency = math.log(
                    1 + (len(corpus) - frequency + 0.5) / (frequency + 0.5)
                )
                score += (
                    inverse_frequency
                    * count
                    * 2.5
                    / (count + 1.5 * (0.25 + 0.75 * len(document) / max(average_length, 1.0)))
                )
        ranked.append((float("inf") if exact else score, definition.name))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in ranked[:limit]]
