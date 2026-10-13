from typing import Any

from lonora_contracts.chart import ChartState
from lonora_core.chart_annotations import validate_annotations

from .schema import CloudChartRow
from .transactions import ResourceRepository


class CloudChartRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for cloud charts."""

    row_type = CloudChartRow
    kind = "cloud_charts"
    payload_model = ChartState

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        validated = super().validate(payload)
        validate_annotations(validated.get("annotations", []))
        return validated
