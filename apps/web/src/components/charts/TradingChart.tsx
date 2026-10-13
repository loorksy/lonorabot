import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  LineSeries,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { ChartScene } from "../../lib/charts";

/** Render the server scene; market history and indicator calculations stay in Python. */
export function TradingChart({ scene }: { scene: ChartScene }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candles = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lines = useRef<ISeriesApi<"Line">[]>([]);
  const priceLines = useRef<IPriceLine[]>([]);
  const linePalette = useRef<string[]>([]);
  const binding = useRef("");

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const instance = createChart(element, {
      autoSize: true,
      height: 420,
      timeScale: { timeVisible: true },
      localization: { locale: document.documentElement.lang },
    });
    const candleSeries = instance.addSeries(CandlestickSeries, { borderVisible: false });
    chart.current = instance;
    candles.current = candleSeries;
    const paint = () => {
      const tokens = getComputedStyle(element);
      const color = (name: string) => tokens.getPropertyValue(name).trim();
      instance.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: color("--card") },
          textColor: color("--muted-foreground"),
        },
        grid: {
          vertLines: { color: color("--border") },
          horzLines: { color: color("--border") },
        },
        rightPriceScale: { borderColor: color("--border") },
        localization: { locale: document.documentElement.lang },
      });
      for (const [index, line] of lines.current.entries())
        line.applyOptions({ color: color(linePalette.current[index]) });
      candleSeries.applyOptions({
        upColor: color("--success"),
        downColor: color("--destructive"),
        wickUpColor: color("--success"),
        wickDownColor: color("--destructive"),
      });
    };
    paint();
    const theme = new MutationObserver(paint);
    theme.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "lang"],
    });
    return () => {
      theme.disconnect();
      instance.remove();
      chart.current = null;
      candles.current = null;
      lines.current = [];
      linePalette.current = [];
      priceLines.current = [];
      binding.current = "";
    };
  }, []);

  useEffect(() => {
    const instance = chart.current;
    const candleSeries = candles.current;
    if (!instance || !candleSeries || !container.current) return;
    const sameBinding = binding.current === `${scene.symbol}:${scene.timeframe}`;
    const viewport = sameBinding ? instance.timeScale().getVisibleLogicalRange() : null;
    candleSeries.setData(
      scene.candles.map((c) => ({
        time: Math.floor(new Date(c.time).getTime() / 1000) as UTCTimestamp,
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
      })),
    );
    for (const line of lines.current) instance.removeSeries(line);
    lines.current = [];
    linePalette.current = [];
    const tokens = getComputedStyle(container.current);
    const palette = ["--link", "--warning", "--foreground"];
    const colors = palette.map((name) => tokens.getPropertyValue(name).trim());
    let nextPane = 1;
    for (const [index, indicator] of scene.indicators.entries()) {
      const pane = ["RSI", "MACD", "ATR"].includes(indicator.name.toUpperCase()) ? nextPane++ : 0;
      for (const [name, values] of Object.entries(indicator.series)) {
        const line = instance.addSeries(
          LineSeries,
          {
            color: colors[index % colors.length],
            lineWidth: 1,
            title: `${indicator.name} ${indicator.period} ${name}`,
          },
          pane,
        );
        lines.current.push(line);
        linePalette.current.push(palette[index % palette.length]);
        line.setData(
          values.flatMap((value, candleIndex) =>
            value === null || !scene.candles[candleIndex]
              ? []
              : [
                  {
                    time: Math.floor(
                      new Date(scene.candles[candleIndex].time).getTime() / 1000,
                    ) as UTCTimestamp,
                    value,
                  },
                ],
          ),
        );
      }
    }
    for (const priceLine of priceLines.current) candleSeries.removePriceLine(priceLine);
    priceLines.current = [];
    for (const annotation of scene.annotations) {
      if (
        ["price", "horizontal_line"].includes(String(annotation.type)) &&
        Number.isFinite(Number(annotation.price))
      )
        priceLines.current.push(
          candleSeries.createPriceLine({
            price: Number(annotation.price),
            color: String(annotation.color ?? tokens.getPropertyValue("--warning").trim()),
            lineWidth: 1,
            title: String(annotation.label ?? annotation.text ?? ""),
          }),
        );
    }
    if (viewport) instance.timeScale().setVisibleLogicalRange(viewport);
    else instance.timeScale().fitContent();
    binding.current = `${scene.symbol}:${scene.timeframe}`;
  }, [scene]);
  return <div className="chart-renderer" ref={container} dir="ltr" />;
}
