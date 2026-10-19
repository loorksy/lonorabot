import type {
  Bar,
  IBasicDataFeed,
  ResolutionString,
  SubscribeBarsCallback,
} from "../../public/charting_library/charting_library";
import type { ChartScene } from "./charts";

export function chartResolution(frame: string): ResolutionString {
  if (frame === "1mn") return "1M" as ResolutionString;
  if (frame.endsWith("h")) return String(Number.parseInt(frame, 10) * 60) as ResolutionString;
  if (frame.endsWith("d")) return `${Number.parseInt(frame, 10)}D` as ResolutionString;
  if (frame.endsWith("w")) return `${Number.parseInt(frame, 10)}W` as ResolutionString;
  return String(Number.parseInt(frame, 10)) as ResolutionString;
}
export function chartBars(scene: ChartScene): Bar[] {
  const bars = new Map<number, Bar>();
  for (const candle of scene.candles) {
    const bar = {
      time: Date.parse(candle.time),
      open: Number(candle.open),
      high: Number(candle.high),
      low: Number(candle.low),
      close: Number(candle.close),
    };
    if (Object.values(bar).every(Number.isFinite)) bars.set(bar.time, bar);
  }
  return [...bars.values()].sort((a, b) => a.time - b.time);
}
/** Scene history and subscriptions share Lonora's exact broker binding. No external quotes. */
export class SceneDatafeed {
  scene: ChartScene;
  private subscribers = new Map<string, { receive: SubscribeBarsCallback; reset: () => void }>();
  onCorrection?: () => Promise<void>;
  settled: Promise<void> = Promise.resolve();
  constructor(scene: ChartScene) {
    this.scene = scene;
  }
  readonly api: IBasicDataFeed = {
    onReady: (receive) =>
      setTimeout(
        () =>
          receive({
            supported_resolutions: [chartResolution(this.scene.timeframe)],
            supports_time: false,
          }),
        0,
      ),
    searchSymbols: (_input, _exchange, _type, receive) => receive([]),
    resolveSymbol: (name, receive, fail) =>
      setTimeout(() => {
        if (name !== this.scene.symbol) {
          fail("unknown_symbol");
          return;
        }
        receive({
          name,
          ticker: name,
          description: name,
          type: "unknown",
          session: "24x7",
          timezone: "Etc/UTC",
          exchange: "Lonora",
          listed_exchange: "Lonora",
          minmov: 1,
          // Generic display precision only. Scene candles do not carry broker tick-size metadata.
          pricescale: 100000000,
          has_intraday: true,
          has_daily: true,
          has_weekly_and_monthly: true,
          supported_resolutions: [chartResolution(this.scene.timeframe)],
          volume_precision: 0,
          format: "price",
          data_status: "streaming",
        });
      }, 0),
    getBars: (symbol, resolution, period, receive, fail) =>
      setTimeout(() => {
        if (
          symbol.ticker !== this.scene.symbol ||
          resolution !== chartResolution(this.scene.timeframe)
        ) {
          fail("chart_scope_mismatch");
          return;
        }
        const all = chartBars(this.scene);
        // First request may need countBack bars before `from`; never manufacture missing history.
        let selected = all.filter(
          (bar) => bar.time < period.to * 1000 && bar.time >= period.from * 1000,
        );
        if (period.firstDataRequest && selected.length < period.countBack)
          selected = all.filter((bar) => bar.time < period.to * 1000).slice(-period.countBack);
        receive(selected, { noData: selected.length === 0 });
      }, 0),
    subscribeBars: (symbol, resolution, receive, id, reset) => {
      if (
        symbol.ticker === this.scene.symbol &&
        resolution === chartResolution(this.scene.timeframe)
      )
        this.subscribers.set(id, { receive, reset });
    },
    unsubscribeBars: (id) => {
      this.subscribers.delete(id);
    },
  };
  update(next: ChartScene) {
    const previous = chartBars(this.scene);
    const incoming = chartBars(next);
    this.scene = next;
    const last = previous.at(-1);
    if (!last) {
      this.settled = this.onCorrection?.() ?? Promise.resolve();
      return;
    }
    const byTime = new Map(incoming.map((bar) => [bar.time, bar]));
    const corrected =
      previous.some(
        (bar) =>
          bar.time < last.time && JSON.stringify(bar) !== JSON.stringify(byTime.get(bar.time)),
      ) || !byTime.has(last.time);
    if (corrected) {
      for (const subscriber of this.subscribers.values()) subscriber.reset();
      this.settled = this.onCorrection?.() ?? Promise.resolve();
      return;
    }
    for (const bar of incoming.filter((bar) => bar.time >= last.time))
      for (const subscriber of this.subscribers.values()) subscriber.receive(bar);
  }
}
