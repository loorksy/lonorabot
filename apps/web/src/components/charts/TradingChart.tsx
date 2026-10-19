import { Trans } from "@lingui/react/macro";
import { useEffect, useRef, useState } from "react";
import type {
  ChartingLibraryWidgetOptions,
  EntityId,
  IChartingLibraryWidget,
  IChartWidgetApi,
  VisiblePriceRange,
  VisibleTimeRange,
} from "../../../public/charting_library/charting_library";
import type { ChartScene } from "../../lib/charts";
import { drawingVisible, renderDrawing } from "../../lib/tradingview-drawings";
import { chartResolution, SceneDatafeed } from "../../lib/tradingview-feed";
import { sceneStudies } from "../../lib/tradingview-studies";

declare global {
  interface Window {
    TradingView?: { widget: new (options: ChartingLibraryWidgetOptions) => IChartingLibraryWidget };
  }
}
let script: Promise<void> | undefined;
function loadLibrary() {
  if (window.TradingView) return Promise.resolve();
  if (!script)
    script = new Promise<void>((resolve, reject) => {
      const element = document.createElement("script");
      element.src = "/charting_library/charting_library.standalone.js";
      element.onload = () => resolve();
      element.onerror = () => {
        element.remove();
        script = undefined;
        reject(new Error("chart_library_unavailable"));
      };
      document.head.appendChild(element);
    });
  return script;
}

type Viewport = { time: VisibleTimeRange; price: VisiblePriceRange | null; auto: boolean };
const savedViewports = new Map<string, Viewport>();
function captureViewport(chart: IChartWidgetApi): Viewport {
  const scale = chart
    .getPanes()[0]
    ?.getRightPriceScales()
    .find((scale) => scale.hasMainSeries());
  return {
    time: chart.getVisibleRange(),
    price: scale?.getVisiblePriceRange() ?? null,
    auto: scale?.isAutoScale() ?? true,
  };
}
async function restoreViewport(chart: IChartWidgetApi, view: Viewport) {
  await chart.setVisibleRange(view.time);
  const scale = chart
    .getPanes()[0]
    ?.getRightPriceScales()
    .find((scale) => scale.hasMainSeries());
  scale?.setAutoScale(view.auto);
  if (!view.auto && view.price) scale?.setVisiblePriceRange(view.price);
}

/** The sole chart renderer. Quotes, studies and saved geometry come from Lonora scenes. */
export function TradingChart({
  scene,
  accountId,
  onApplied,
}: {
  scene: ChartScene;
  accountId?: string;
  onApplied?: (scene: ChartScene) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const widget = useRef<IChartingLibraryWidget | undefined>(undefined);
  const feed = useRef<SceneDatafeed | undefined>(undefined);
  const current = useRef(scene);
  current.current = scene;
  const applied = useRef(onApplied);
  applied.current = onApplied;
  const draw = useRef<(() => void) | undefined>(undefined);
  const [locale, setLocale] = useState<"en" | "ar">(
    document.documentElement.lang === "ar" ? "ar" : "en",
  );
  const [error, setError] = useState("");
  const [themeError, setThemeError] = useState(false);
  const following = useRef(false);
  const [followAgent, setFollowAgent] = useState(false);
  const focusAnalysis = useRef<(() => void) | undefined>(undefined);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setLocale(document.documentElement.lang === "ar" ? "ar" : "en");
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    return () => observer.disconnect();
  }, []);
  const studyBinding = JSON.stringify(
    scene.indicators.map((study) => [study.name, study.period, Object.keys(study.series)]),
  );
  const binding = `${scene.chart_id}:${scene.symbol}:${scene.timeframe}`;
  useEffect(() => {
    void studyBinding; // A structural study edit rebuilds metadata; quote updates never remount.
    let disposed = false;
    let instance: IChartingLibraryWidget | undefined;
    let generation = 0;
    let frameDocument: Document | null = null;
    let themeObserver: MutationObserver | undefined;
    let themeRequest = 0;
    const freeBrowse = () => {
      following.current = false;
      setFollowAgent(false);
    };
    let focusedSignature = "";
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") window.dispatchEvent(new CustomEvent("lonora:chart-escape"));
    };
    const layers = new Map<string, { signature: string; ids: EntityId[] }>();
    container.current?.removeAttribute("data-applied-scene-version");
    setReady(false);
    setError("");
    setThemeError(false);
    const source = new SceneDatafeed(current.current);
    feed.current = source;
    void loadLibrary()
      .then(() => {
        if (disposed || !container.current || !window.TradingView) return;
        instance = new window.TradingView.widget({
          container: container.current,
          library_path: "/charting_library/",
          datafeed: source.api,
          symbol: source.scene.symbol,
          interval: chartResolution(source.scene.timeframe),
          locale,
          autosize: true,
          timezone: "Etc/UTC",
          theme: document.documentElement.dataset.theme === "light" ? "light" : "dark",
          disabled_features: [
            "header_widget",
            "uppercase_instrument_names",
            "create_volume_indicator_by_default",
            "left_toolbar",
            "control_bar",
            "timeframes_toolbar",
            "context_menus",
            "use_localstorage_for_settings",
            "save_chart_properties_to_local_storage",
          ],
          custom_indicators_getter: async (pine) => sceneStudies(source, pine),
          enabled_features: ["hide_left_toolbar_by_default"],
        });
        widget.current = instance;
        instance.onChartReady(async () => {
          if (disposed || !instance) return;
          // The vendor's inner-frame theme API exists only after onChartReady.
          // Keep the observer with its widget so queued mutations cannot target a replacement.
          const syncTheme = async () => {
            if (disposed || !instance) return;
            const request = ++themeRequest;
            try {
              await instance.changeTheme(
                document.documentElement.dataset.theme === "light" ? "light" : "dark",
              );
              if (!disposed && request === themeRequest) setThemeError(false);
            } catch {
              if (!disposed && request === themeRequest) setThemeError(true);
            }
          };
          themeObserver = new MutationObserver(() => {
            void syncTheme();
          });
          themeObserver.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-theme"],
          });
          void syncTheme();
          frameDocument = container.current?.querySelector("iframe")?.contentDocument ?? null;
          frameDocument?.addEventListener("keydown", handleEscape, true);
          frameDocument?.addEventListener("pointerdown", freeBrowse, true);
          frameDocument?.addEventListener("wheel", freeBrowse, true);
          const chart = instance.activeChart();
          focusAnalysis.current = () => {
            const next = source.scene;
            const agent = next.annotations.filter(
              (a) => a.source === "agent" && drawingVisible(a, next, accountId),
            );
            if (!agent.length) return;
            const anchors = agent
              .flatMap((a) => [a.start, a.end, a.parallel, a])
              .flatMap((value) => {
                const anchor = value as { time?: string; price?: number } | undefined;
                return anchor?.time && Number.isFinite(Date.parse(anchor.time))
                  ? [Date.parse(anchor.time) / 1000]
                  : [];
              });
            const recent = next.candles.slice(-75).map((candle) => Date.parse(candle.time) / 1000);
            const times = anchors.length > 1 ? anchors : recent;
            if (times.length < 2) return;
            const from = Math.min(...times),
              to = Math.max(...times);
            const margin = Math.max(60, (to - from) * 0.12);
            void chart
              .setVisibleRange({ from: from - margin, to: to + margin })
              .catch(() => setError("chart_focus_failed"));
          };
          const studiesReady = Promise.all(
            source.scene.indicators.map((indicator, index) =>
              chart.createStudy(
                `Lonora ${indicator.name} ${indicator.period} (${index + 1})`,
                false,
                true,
              ),
            ),
          );
          source.onCorrection = () => {
            const range = captureViewport(chart);
            return new Promise<void>((resolve) => {
              chart.onDataLoaded().subscribe(
                null,
                () => {
                  void restoreViewport(chart, range)
                    .catch(() => {})
                    .finally(resolve);
                },
                true,
              );
              chart.resetData();
            });
          };
          const apply = async () => {
            const run = ++generation;
            const next = source.scene;
            const used = new Set<string>();
            try {
              await studiesReady;
              await source.settled;
              if (disposed || run !== generation) return;
              for (const [index, a] of next.annotations.entries()) {
                if (!drawingVisible(a, next, accountId)) continue;
                const key = String(a.id ?? `legacy:${index}`),
                  signature = JSON.stringify(a);
                used.add(key);
                if (layers.get(key)?.signature === signature) continue;
                const ids = await renderDrawing(chart, a, next);
                if (disposed || run !== generation) {
                  for (const id of ids) chart.removeEntity(id);
                  return;
                }
                for (const id of layers.get(key)?.ids ?? []) chart.removeEntity(id);
                layers.set(key, { signature, ids });
              }
              for (const [key, layer] of layers)
                if (!used.has(key)) {
                  for (const id of layer.ids) chart.removeEntity(id);
                  layers.delete(key);
                }
              await new Promise<void>((resolve) => {
                if (chart.dataReady(resolve)) resolve();
              });
              await new Promise<void>((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
              );
              if (disposed || run !== generation) return;
              const agentSignature = JSON.stringify(
                next.annotations.filter((a) => a.source === "agent"),
              );
              if (following.current && focusedSignature !== agentSignature)
                focusAnalysis.current?.();
              focusedSignature = agentSignature;
              setError("");
              container.current?.setAttribute(
                "data-applied-scene-version",
                String(next.scene_version),
              );
              applied.current?.(next);
            } catch {
              if (!disposed) setError("chart_drawing_failed");
            }
          };
          draw.current = () => {
            void apply();
          };
          const view = savedViewports.get(binding);
          if (view) await restoreViewport(chart, view).catch(() => {});
          if (disposed) return;
          setReady(true);
          void apply();
        });
      })
      .catch(() => {
        if (!disposed) setError("chart_library_unavailable");
      });
    return () => {
      disposed = true;
      themeObserver?.disconnect();
      frameDocument?.removeEventListener("keydown", handleEscape, true);
      frameDocument?.removeEventListener("pointerdown", freeBrowse, true);
      frameDocument?.removeEventListener("wheel", freeBrowse, true);
      generation++;
      if (instance) {
        try {
          savedViewports.set(binding, captureViewport(instance.activeChart()));
          if (savedViewports.size > 20)
            savedViewports.delete(savedViewports.keys().next().value ?? "");
        } catch {
          /* Loading was interrupted. */
        }
        instance.remove();
      }
      widget.current = undefined;
      feed.current = undefined;
      draw.current = undefined;
      focusAnalysis.current = undefined;
    };
  }, [binding, locale, accountId, studyBinding]);
  useEffect(() => {
    feed.current?.update(scene);
    draw.current?.();
  }, [scene]);
  return (
    <div className="trading-chart-surface" dir="ltr">
      <div className="chart-renderer" ref={container} data-renderer="tradingview" />
      {!ready && !error && (
        <p role="status">
          <Trans>Loading chart…</Trans>
        </p>
      )}
      {error && (
        <p role="alert">
          <Trans>Chart could not be displayed.</Trans> <code>{error}</code>
        </p>
      )}
      {themeError && (
        <p role="alert">
          <Trans>Chart appearance could not be updated.</Trans> <code>chart_theme_failed</code>
        </p>
      )}
      <div className="chart-view-controls">
        <button
          type="button"
          onClick={() => {
            following.current = false;
            setFollowAgent(false);
            widget.current?.activeChart().executeActionById("timeScaleReset");
          }}
        >
          <Trans>Follow live</Trans>
        </button>
        <button type="button" onClick={() => focusAnalysis.current?.()}>
          <Trans>Show Agent analysis</Trans>
        </button>
        <button
          type="button"
          aria-pressed={followAgent}
          onClick={() => {
            const next = !followAgent;
            following.current = next;
            setFollowAgent(next);
            if (next) focusAnalysis.current?.();
          }}
        >
          {followAgent ? <Trans>Free Browse</Trans> : <Trans>Follow Agent</Trans>}
        </button>
      </div>
    </div>
  );
}
