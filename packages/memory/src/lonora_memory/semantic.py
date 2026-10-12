import math

from lonora_core.user_error import LonoraError


def cosine_similarity(first: list[float], second: list[float]) -> float:
    if not first or len(first) != len(second) or any(not math.isfinite(v) for v in first + second):
        raise LonoraError("invalid_embedding")
    norm = math.sqrt(sum(x * x for x in first) * sum(x * x for x in second))
    return sum(a * b for a, b in zip(first, second, strict=True)) / norm if norm else 0.0


def semantic_retrieve(
    query: list[float], documents: list[tuple[str, list[float]]], limit: int = 5
) -> list[str]:
    scored = sorted(
        ((cosine_similarity(query, vector), text) for text, vector in documents), reverse=True
    )
    return [text for _, text in scored[:limit]]
