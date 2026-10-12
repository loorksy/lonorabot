from lonora_contracts.chart import ChartState

from .schema import CloudChartRow
from .transactions import ResourceRepository


class CloudChartRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for cloud charts."""

    row_type = CloudChartRow
    kind = "cloud_charts"
    payload_model = ChartState
