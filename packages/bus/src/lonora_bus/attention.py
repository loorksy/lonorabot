"""Translated mandatory alerts; optional runtime chatter stays in the app."""

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast


@lru_cache(maxsize=1)
def catalogs() -> dict[str, dict[str, str]]:
    return cast(
        dict[str, dict[str, str]],
        json.loads(
            files("lonora_bus").joinpath("attention_messages.json").read_text(encoding="utf-8")
        ),
    )


def attention_text(code: str, locale: str, parameters: Mapping[str, Any] | None = None) -> str:
    catalog = catalogs().get(locale, catalogs()["ar"])
    if code == "model_access_failed" and parameters:
        # The provider's fixed name and the failure family; never the provider's message.
        family = catalog.get(code + "_" + str(parameters.get("reason")))
        if family:
            name = parameters.get("provider_name") or catalog["model_access_endpoint"]
            return family.replace("{provider}", str(name))
    return catalog.get(code, catalog["internal_update"])
