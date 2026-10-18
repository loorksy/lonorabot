"""Prepare provider-independent encoding caches during setup/build, not requests."""

import tiktoken

for name in ("cl100k_base", "o200k_base"):
    tiktoken.get_encoding(name)
    print("Verified tokenizer cache:", name)
