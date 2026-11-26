"""Lonora's fixed model list (VISION 12.4), as the data a release ships.

``lonora_providers/models.json`` is written by ``scripts/import_model_catalog.py`` from
``@earendil-works/pi-ai``, the list Rakazo pins, and changes only with a Lonora release.
The file is read here, below every package that uses it, so the usage view's prices
(``model_pricing``) and the providers' catalog (``lonora_providers.catalog``, which turns
the entries into model descriptors) read one copy. Nothing asks a provider for its list.
"""

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    text = files("lonora_providers").joinpath("models.json").read_text(encoding="utf-8")
    return cast(dict[str, Any], json.loads(text))


@lru_cache(maxsize=1)
def _index() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (provider, cast(str, entry["id"]).lower()): entry
        for provider, entries in cast(dict[str, list[dict[str, Any]]], _data()["providers"]).items()
        for entry in entries
    }


def list_package() -> str:
    """The package and version the list was imported from (``@earendil-works/pi-ai@1.6.0``)."""
    return str(_data()["source"]).split(" ", 1)[0]


def listed_entries(provider: str) -> list[dict[str, Any]]:
    """One provider's shipped entries, sorted by id. A provider the list does not hold
    (the owner's own endpoint, whose models are the owner's) has none."""
    providers = cast(dict[str, list[dict[str, Any]]], _data()["providers"])
    return list(providers.get(provider, []))


def listed_entry(provider: str, model: str) -> dict[str, Any] | None:
    """The shipped entry of one model, matched without regard to case."""
    return _index().get((provider, model.lower()))
