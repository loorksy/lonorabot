"""Translated mandatory alerts; optional runtime chatter stays in the app."""

import json
from functools import lru_cache
from importlib.resources import files
from typing import cast


@lru_cache(maxsize=1)
def catalogs() -> dict[str, dict[str, str]]:
    return cast(
        dict[str, dict[str, str]],
        json.loads(
            files("lonora_bus").joinpath("attention_messages.json").read_text(encoding="utf-8")
        ),
    )


def attention_text(code: str, locale: str) -> str:
    catalog = catalogs().get(locale, catalogs()["ar"])
    return catalog.get(code, catalog["internal_update"])
