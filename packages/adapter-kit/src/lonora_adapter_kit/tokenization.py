"""Offline request estimates using hash-verified, setup-cached tiktoken data.

The hashes are the upstream tiktoken 0.12.0 encoding hashes. Missing/corrupt
cache data falls back to UTF-8 bytes; request admission never downloads data.
"""

import hashlib
import os
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import tiktoken

_ENCODINGS = {
    "cl100k_base": "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    "o200k_base": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
}


@lru_cache(maxsize=2)
def cached_encoding(name: str) -> tiktoken.Encoding | None:
    if name not in _ENCODINGS:
        return None
    cache = os.environ.get("TIKTOKEN_CACHE_DIR", os.environ.get("DATA_GYM_CACHE_DIR"))
    if cache == "":
        return None
    root = Path(cache) if cache else Path(tempfile.gettempdir()) / "data-gym-cache"
    url = f"https://openaipublic.blob.core.windows.net/encodings/{name}.tiktoken"
    key = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()
    try:
        if hashlib.sha256((root / key).read_bytes()).hexdigest() != _ENCODINGS[name]:
            return None
    except OSError:
        return None
    return tiktoken.get_encoding(name)


def text_counter(provider: str, model: str) -> tuple[str, Callable[[str], int]]:
    name = "cl100k_base"
    matched = False
    if provider == "openai":
        try:
            name = tiktoken.encoding_name_for_model(model)
            matched = True
        except KeyError:
            pass
    if name not in _ENCODINGS:
        name, matched = "cl100k_base", False
    encoding = cached_encoding(name)
    if encoding is None:
        return "utf8_bytes_fallback_v1", lambda text: len(text.encode("utf-8"))

    def count(text: str) -> int:
        # A text tokenizer does not exactly describe provider framing/vision.
        # Proxy tokenization for other providers additionally reserves 20%.
        size = len(encoding.encode(text, disallowed_special=()))
        return size if matched else (size * 6 + 4) // 5

    return name + ("_text_v1" if matched else "_proxy_margin20_v1"), count
