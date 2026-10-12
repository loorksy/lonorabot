from typing import Any

from lonora_core.user_error import LonoraError


def validate_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(annotations) > 100:
        raise LonoraError("too_many_chart_annotations")
    for annotation in annotations:
        if annotation.get("type") not in {"horizontal_line", "trend_line", "note"}:
            raise LonoraError("unsupported_annotation")
    return annotations
