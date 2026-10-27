"""Regenerate compact model-facing vocabulary from the actual native contract.

Use --check during builds. No provider, browser, database or network is involved.
Authored semantics/examples surround the generated property/enum/arity/limit block.
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from lonora_agent.skills.visual_policy import MAX_VISUAL_GUIDANCE_CHARS
from lonora_contracts.visual_response import (
    ALLOWED,
    COMMON,
    KEY,
    MAX_VISUAL_BYTES,
    MAX_VISUAL_DEPTH,
    MAX_VISUAL_EXPRESSION_DEPTH,
    MAX_VISUAL_NODES,
    OPERATOR_ARITY,
    RichContent,
    VisualAction,
    VisualDocument,
    VisualNode,
)

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "packages/agent-runtime/resources/prompts/native_visual_response.md"
START = "<!-- native-visual:generated -->"
END = "<!-- /native-visual:generated -->"


def _constraint(value: dict[str, Any], key: str) -> int | float | None:
    if key in value:
        return value[key]
    for candidate in value.get("anyOf", []):
        if key in candidate:
            return candidate[key]
    return None


def generated_reference() -> str:
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for name, fields in ALLOWED.items():
        groups[tuple(sorted(fields))].append(name)
    lines = [
        START,
        "Native contract v1. Every node requires unique id,type. Common properties: "
        + ",".join(sorted(COMMON))
        + ". Additional allowed properties:",
    ]
    lines.extend(
        ",".join(names) + ": " + (",".join(fields) or "none") for fields, names in groups.items()
    )
    enums = {
        name: get_args(field.annotation)
        for name, field in VisualNode.model_fields.items()
        if name != "type" and get_origin(field.annotation) is Literal
    }
    enums["mode"] = get_args(VisualDocument.model_fields["mode"].annotation)
    enums["action.kind"] = get_args(VisualAction.model_fields["kind"].annotation)
    lines.append("Enums: " + "; ".join(k + "=" + "|".join(v) for k, v in enums.items()) + ".")
    arities: dict[tuple[int, int], list[str]] = defaultdict(list)
    for name, arity in sorted(OPERATOR_ARITY.items()):
        arities[arity].append(name)
    lines.append(
        "Operator argument counts: "
        + "; ".join(
            ",".join(names) + f"={lo}" + (f"..{hi}" if lo != hi else "")
            for (lo, hi), names in sorted(arities.items())
        )
        + "."
    )
    node = VisualNode.model_json_schema()["$defs"]["VisualNode"]["properties"]
    document = VisualDocument.model_json_schema()["properties"]
    reply = RichContent.model_json_schema()["properties"]
    limits = [
        f"bytes={MAX_VISUAL_BYTES}",
        f"nodes={MAX_VISUAL_NODES}",
        f"treeDepth={MAX_VISUAL_DEPTH}",
        f"expressionDepth={MAX_VISUAL_EXPRESSION_DEPTH}",
        f"stateKeys={document['state']['maxProperties']}",
        f"replyParts={reply['parts']['maxItems']}",
    ]
    for name, value in node.items():
        maximum = _constraint(value, "maxItems")
        if maximum is not None:
            limits.append(f"{name}={maximum}")
        maximum = _constraint(value, "maxLength")
        if maximum is not None and name in {"text", "label"}:
            limits.append(f"{name}Chars={maximum}")
        if "minimum" in value and "maximum" in value:
            limits.append(f"{name}={value['minimum']}..{value['maximum']}")
    lines.append("Limits: " + "; ".join(limits) + ". Key pattern: " + KEY.pattern + ".")
    lines.append(END)
    return "\n".join(lines)


def export() -> str:
    text = GUIDE.read_text()
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("native_visual_reference_markers_invalid")
    start = text.index(START)
    end = text.index(END, start) + len(END)
    result = text[:start] + generated_reference() + text[end:]
    if len(result.strip()) > MAX_VISUAL_GUIDANCE_CHARS:
        raise ValueError("native_visual_reference_oversized")
    for line in result.splitlines():
        if line.startswith('{"version"'):
            VisualDocument.model_validate(json.loads(line))
    if re.search(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]", result):
        raise ValueError("native_visual_reference_language_invalid")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = export()
    if args.check:
        if GUIDE.read_text() != result:
            raise SystemExit(
                "Native visual vocabulary is stale; run scripts/export_native_visual_reference.py"
            )
    else:
        GUIDE.write_text(result)
    print(f"Native visual vocabulary: {len(result.strip())} characters; live contract verified")


if __name__ == "__main__":
    main()
