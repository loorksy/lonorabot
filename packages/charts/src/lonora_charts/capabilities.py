from lonora_core.chart_controller import TIMEFRAMES
from lonora_core.chart_indicator import SUPPORTED


def chart_capabilities() -> dict[str, list[str]]:
    return {"timeframes": sorted(TIMEFRAMES), "indicators": sorted(SUPPORTED)}
