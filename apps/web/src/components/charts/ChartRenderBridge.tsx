import { useEffect, useRef, useState } from "react";
import { activateLocale } from "../../i18n/config";
import type { ChartScene } from "../../lib/charts";
import { TradingChart } from "./TradingChart";

declare global {
  interface Window {
    ReactNativeWebView?: { postMessage: (message: string) => void };
  }
}
function notify(message: Record<string, unknown>) {
  if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(message));
  else if (window.parent !== window) window.parent.postMessage(message, window.location.origin);
}
/** Credential-free renderer: the authenticated host supplies bounded owned scenes. */
export function ChartRenderBridge() {
  const [scene, setScene] = useState<ChartScene>();
  const accepted = useRef<ChartScene | undefined>(undefined);
  const [accountId, setAccountId] = useState<string>();
  useEffect(() => {
    const locale = new URLSearchParams(window.location.search).get("locale") === "ar" ? "ar" : "en";
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
    const receive = (event: MessageEvent) => {
      if (
        event.origin !== window.location.origin ||
        (event.source !== window.parent && event.source !== window)
      )
        return;
      const value = event.data;
      if (value?.type !== "lonora.chart.scene") return;
      const next = value.scene as ChartScene | undefined;
      if (
        !next ||
        typeof next.chart_id !== "string" ||
        typeof next.symbol !== "string" ||
        typeof next.timeframe !== "string" ||
        !Number.isInteger(next.scene_version) ||
        !Number.isInteger(next.revision) ||
        next.scene_version < 0 ||
        next.revision < 0 ||
        !Array.isArray(next.candles) ||
        next.candles.length > 10000 ||
        !Array.isArray(next.annotations) ||
        next.annotations.length > 500 ||
        !Array.isArray(next.indicators)
      )
        return;
      if (
        next.candles.some(
          (candle) =>
            !candle ||
            !Number.isFinite(Date.parse(candle.time)) ||
            ![candle.open, candle.high, candle.low, candle.close].every((price) =>
              Number.isFinite(Number(price)),
            ),
        )
      )
        return;
      if (
        next.indicators.length > 32 ||
        next.indicators.some(
          (indicator) =>
            !indicator ||
            typeof indicator.name !== "string" ||
            !indicator.series ||
            Object.values(indicator.series).some(
              (values) =>
                !Array.isArray(values) ||
                values.length > 10000 ||
                values.some((value) => value !== null && !Number.isFinite(value)),
            ),
        )
      )
        return;
      const old = accepted.current;
      if (
        old?.chart_id === next.chart_id &&
        (old.scene_version > next.scene_version || old.revision > next.revision)
      )
        return;
      accepted.current = next;
      if (value.locale === "en" || value.locale === "ar") activateLocale(value.locale);
      setAccountId(typeof value.account_id === "string" ? value.account_id : undefined);
      setScene(next);
    };
    const handleEscape = () => notify({ type: "lonora.chart.escape" });
    window.addEventListener("lonora:chart-escape", handleEscape);
    window.addEventListener("message", receive);
    notify({ type: "lonora.chart.ready" });
    return () => {
      window.removeEventListener("message", receive);
      window.removeEventListener("lonora:chart-escape", handleEscape);
    };
  }, []);
  return (
    <main className="chart-render-bridge">
      {scene && (
        <TradingChart
          scene={scene}
          accountId={accountId}
          onApplied={(applied) =>
            notify({
              type: "lonora.chart.applied",
              chart_id: applied.chart_id,
              scene_version: applied.scene_version,
              data_revision: applied.data_revision,
            })
          }
        />
      )}
    </main>
  );
}
