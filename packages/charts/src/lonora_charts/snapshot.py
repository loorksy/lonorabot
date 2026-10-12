from html import escape

from lonora_contracts.market import Candle
from lonora_core.user_error import LonoraError


def svg_snapshot(symbol: str, candles: list[Candle], width: int = 960, height: int = 480) -> str:
    if len(candles) < 2:
        raise LonoraError("chart_data_unavailable", 409)
    values = [float(c.close) for c in candles]
    low, high = min(values), max(values)
    scale = high - low or 1
    points = " ".join(
        f"{30 + i * (width - 60) / (len(values) - 1):.2f},{height - 30 - (value - low) * (height - 70) / scale:.2f}"
        for i, value in enumerate(values)
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#111215"/><text x="30" y="25" fill="#ececee">{escape(symbol)}</text><polyline fill="none" stroke="#7c83fd" stroke-width="2" points="{points}"/></svg>'
