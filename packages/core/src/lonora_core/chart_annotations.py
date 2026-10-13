from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from lonora_core.user_error import LonoraError


def validate_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(annotations) > 100:
        raise LonoraError("too_many_chart_annotations")
    for annotation in annotations:
        kind = annotation.get("type")
        if kind not in {"price", "horizontal_line", "trend_line", "note"}:
            raise LonoraError("unsupported_annotation")
        if len(str(annotation.get("label", annotation.get("text", "")))) > 1000:
            raise LonoraError("invalid_chart_annotation")
        try:
            if kind in {"price", "horizontal_line"}:
                price = Decimal(str(annotation["price"]))
                if not price.is_finite() or price <= 0:
                    raise ValueError("invalid_price")
            if kind == "trend_line":
                for point in (annotation["start"], annotation["end"]):
                    price = Decimal(str(point["price"]))
                    timestamp = datetime.fromisoformat(str(point["time"]).replace("Z", "+00:00"))
                    if not price.is_finite() or price <= 0 or timestamp.tzinfo is None:
                        raise ValueError("invalid_point")
        except (KeyError, ValueError, TypeError, InvalidOperation):
            raise LonoraError("invalid_chart_annotation") from None
    return annotations
