"""Write Lonora's fixed model list (VISION 12.4) from the model data Rakazo pins.

    python scripts/import_model_catalog.py --package DIR

DIR is the unpacked ``@earendil-works/pi-ai`` npm tarball (its ``package`` folder). Only
``dist/providers/data/<provider>.json`` and ``package.json`` are read, as JSON data:
nothing in the package is imported or run. The list keeps the chat models of the
providers Lonora supports (pi ``openai-codex`` is Lonora's ``openai_chatgpt``), without
OpenRouter's ``:batch`` ids, as Rakazo filters them for agents (it hides no other id of
these providers). An entry whose wire its provider's adapter does not speak fails the
import, and so does anything that is not the expected shape. The file is written sorted,
so the same package always gives the same bytes.
"""

import argparse
import json
from pathlib import Path
from typing import Any, cast

PACKAGE = "@earendil-works/pi-ai"
TARGET = Path(__file__).resolve().parents[1] / "packages/providers/src/lonora_providers/models.json"
# pi-ai's provider file -> Lonora's provider id (M3).
PROVIDERS = {
    "anthropic": "anthropic",
    "openai": "openai",
    "openai-codex": "openai_chatgpt",
    "deepseek": "deepseek",
    "zai": "zai",
    "openrouter": "openrouter",
}
# The wires (pi-ai's ``api``) each provider's adapter speaks (M5: OpenAI's on the
# Responses API); tests/test_model_list.py checks them against the wires each registered
# adapter declares.
WIRES = {
    "anthropic": {"anthropic-messages"},
    "openai": {"openai-responses"},
    "openai_chatgpt": {"openai-codex-responses"},
    "deepseek": {"openai-completions"},
    "zai": {"openai-completions"},
    # OpenRouter serves its Anthropic entries on Chat Completions as well.
    "openrouter": {"openai-completions", "anthropic-messages"},
}
INPUTS = {"text", "image"}


def fail(message: str) -> SystemExit:
    return SystemExit("import_model_catalog: " + message)


def number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise fail(f"{where} is not a price")
    return value


def count(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise fail(f"{where} is not a positive token count")
    return value


def entry(provider: str, item: dict[str, Any]) -> dict[str, Any]:
    """One chat model in Lonora's shape, after checking every field it keeps."""
    model = item.get("id")
    if not isinstance(model, str) or not model:
        raise fail(f"{provider}: an entry has no id")
    where = f"{provider}/{model}"
    name, wire, inputs = item.get("name"), item.get("api"), item.get("input")
    if not isinstance(name, str) or not name:
        raise fail(f"{where} has no name")
    if wire not in WIRES[provider]:
        raise fail(f"{where} uses the wire {wire!r}, which its adapter does not speak")
    if (
        not isinstance(inputs, list)
        or "text" not in inputs
        or not set(cast(list[Any], inputs)) <= INPUTS
    ):
        raise fail(f"{where} has unexpected inputs")
    if not isinstance(item.get("reasoning"), bool):
        raise fail(f"{where} does not say whether it reasons")
    cost = item.get("cost")
    if not isinstance(cost, dict):
        raise fail(f"{where} has no cost")
    price = cast(dict[str, Any], cost)
    return {
        "id": model,
        "name": name,
        "wire": wire,
        "context_window": count(item.get("contextWindow"), where + " contextWindow"),
        "maximum_output_tokens": count(item.get("maxTokens"), where + " maxTokens"),
        "input": sorted(cast(list[str], inputs), key=["text", "image"].index),
        "reasoning": item["reasoning"],
        "cost": {
            "input": number(price.get("input"), where + " cost.input"),
            "output": number(price.get("output"), where + " cost.output"),
            "cache_read": number(price.get("cacheRead"), where + " cost.cacheRead"),
            "cache_write": number(price.get("cacheWrite"), where + " cost.cacheWrite"),
        },
    }


def provider_models(provider: str, data: Any) -> list[dict[str, Any]]:
    """The provider's chat models, sorted by id; OpenRouter's ``:batch`` ids dropped."""
    if not isinstance(data, dict):
        raise fail(f"{provider}: the data file is not an object")
    models: dict[str, dict[str, Any]] = {}
    for group in cast(dict[str, Any], data).values():
        if not isinstance(group, dict):
            raise fail(f"{provider}: a wire group is not an object")
        for item in cast(dict[str, Any], group).values():
            if not isinstance(item, dict):
                raise fail(f"{provider}: an entry is not an object")
            record = cast(dict[str, Any], item)
            if record.get("type") != "chat":
                continue
            if provider == "openrouter" and str(record.get("id")).endswith(":batch"):
                continue
            converted = entry(provider, record)
            if converted["id"] in models:
                raise fail(f"{provider}/{converted['id']} is listed twice")
            models[converted["id"]] = converted
    if not models:
        raise fail(f"{provider}: no chat model")
    return [models[model] for model in sorted(models)]


def model_list(package: Path) -> dict[str, Any]:
    manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or cast(dict[str, Any], manifest).get("name") != PACKAGE:
        raise fail(f"{package} is not the {PACKAGE} package")
    version = cast(dict[str, Any], manifest).get("version")
    if not isinstance(version, str) or not version:
        raise fail("the package has no version")
    data = package / "dist" / "providers" / "data"
    providers = {
        PROVIDERS[name]: provider_models(
            PROVIDERS[name], json.loads((data / (name + ".json")).read_text(encoding="utf-8"))
        )
        for name in PROVIDERS
    }
    return {
        "source": f"{PACKAGE}@{version} (the list Rakazo pins)",
        "providers": dict(sorted(providers.items())),
    }


def ordered(value: Any) -> Any:
    if isinstance(value, dict):
        items = cast(dict[str, Any], value)
        return {key: ordered(items[key]) for key in sorted(items)}
    if isinstance(value, list):
        return [ordered(item) for item in cast(list[Any], value)]
    return value


def rendered(value: dict[str, Any]) -> str:
    """The source first, as a header; every other key sorted."""
    header = {"source": value["source"], "providers": ordered(value["providers"])}
    return json.dumps(header, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Lonora's fixed model list.")
    parser.add_argument("--package", type=Path, required=True, help="the unpacked package")
    arguments = parser.parse_args()
    value = model_list(cast(Path, arguments.package))
    TARGET.write_text(rendered(value), encoding="utf-8")
    sizes = ", ".join(f"{name} {len(models)}" for name, models in value["providers"].items())
    print(f"Wrote {TARGET.name} from {value['source']}: {sizes}")


if __name__ == "__main__":
    main()
