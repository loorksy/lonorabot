import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { ChartScene } from "../../lib/charts";
export function TradingChart({ scene }: { scene: ChartScene }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const dark = document.documentElement.classList.contains("dark");
    const chart = createChart(container.current, {
      autoSize: true,
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: dark ? "#101011" : "#ffffff" },
        textColor: dark ? "#bcbcc4" : "#404049",
      },
      grid: {
        vertLines: { color: dark ? "#222225" : "#eeeeef" },
        horzLines: { color: dark ? "#222225" : "#eeeeef" },
      },
      timeScale: { timeVisible: true },
      localization: { locale: document.documentElement.lang },
      rightPriceScale: { borderColor: "#44444b" },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#48c9a4",
      downColor: "#f2768a",
      borderVisible: false,
      wickUpColor: "#48c9a4",
      wickDownColor: "#f2768a",
    });
    candles.setData(
      scene.candles.map((c) => ({
        time: Math.floor(new Date(c.time).getTime() / 1000) as UTCTimestamp,
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
      })),
    );
    const colors = ["#a7a3ff", "#fbbf77", "#67c8ff"];
    scene.indicators.forEach((indicator, i) => {
      Object.entries(indicator.series).forEach(([name, values]) => {
        const line = chart.addSeries(LineSeries, {
          color: colors[i % colors.length],
          lineWidth: 1,
          title: `${indicator.name} ${indicator.period} ${name}`,
          priceScaleId: ["RSI", "MACD", "ATR"].includes(indicator.name.toUpperCase())
            ? "oscillator"
            : "right",
        });
        line.setData(
          values.flatMap((value, index) =>
            value === null || !scene.candles[index]
              ? []
              : [
                  {
                    time: Math.floor(
                      new Date(scene.candles[index].time).getTime() / 1000,
                    ) as UTCTimestamp,
                    value,
                  },
                ],
          ),
        );
      });
    });
    scene.annotations.forEach((annotation) => {
      if (annotation.type === "price" && Number.isFinite(Number(annotation.price)))
        candles.createPriceLine({
          price: Number(annotation.price),
          color: String(annotation.color ?? "#d7ab65"),
          lineWidth: 1,
          title: String(annotation.label ?? ""),
        });
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [scene]);
  return <div className="chart-renderer" ref={container} dir="ltr" />;
}
