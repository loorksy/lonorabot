import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Candle, Resource } from "../../lib/api";
import { type ChartScene, type ChartState, charts, readScene } from "../../lib/charts";
import { readCandles } from "../../lib/market";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { SkPage } from "../Skeleton";
import { useSheets } from "../sheets/SheetHost";
import "./agent.css";

const FRAMES = ["5m", "15m", "1h", "4h"] as const;
type Frame = (typeof FRAMES)[number];

type Size = { w: number; h: number };
type Bar = { t: number; o: number; h: number; l: number; c: number };
type Line = { y: number; label?: string; source?: string };
type Segment = { x1: number; y1: number; x2: number; y2: number };

const num = (value: unknown) => Number(value);
const hm = (ms: number) => {
  const d = new Date(ms);
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
};

/** A round price step that puts grid lines ~48px apart (reference chartStep). */
function priceStep(range: number, px: number) {
  const want = Math.max(2, Math.floor(px / 48));
  const raw = range / want;
  const magnitude = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((step) => step >= raw) ?? 10 * magnitude;
}

/* The reference's geometry (chartGeom/drawChart): up to 600 units the drawing scales with the
   width, wider shows more candles; the price axis fits the visible candles with 12% air and
   a round step; labels stay ~10.5px. Drawn from the broker's real candles. */
export function CandleChart({
  candles,
  scene,
  frame,
}: {
  candles: Candle[];
  scene: ChartScene | null;
  frame: Frame;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState<Size>({ w: 600, h: 310 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () =>
      setSize({ w: Math.max(1, el.clientWidth), h: Math.max(1, el.clientHeight) });
    measure();
    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const s = Math.min(1, Math.max(0.55, size.w / 600));
  const VW = Math.round(size.w / s);
  const VH = Math.max(160, Math.round(size.h / s));
  const fs = +(10.5 / s).toFixed(1);
  const gut = Math.round(fs * 3.7 + 14);
  const right = VW - gut;
  const xLast = right - 12;
  const top = Math.round(fs * 0.9);
  const bottom = VH - Math.round(fs * 1.9 + 8);
  const n = Math.max(8, Math.floor((xLast - 20) / 17) + 1);
  const bars: Bar[] = candles.slice(-n).map((c) => ({
    t: Date.parse(c.time),
    o: num(c.open),
    h: num(c.high),
    l: num(c.low),
    c: num(c.close),
  }));
  const X = (i: number) => xLast - (bars.length - 1 - i) * 17;
  let lo = Math.min(...bars.map((b) => b.l));
  let hi = Math.max(...bars.map((b) => b.h));
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
    lo = 0;
    hi = 1;
  }
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.12;
  const p0 = lo - pad;
  const p1 = hi + pad;
  const Y = (price: number) => top + ((p1 - price) / (p1 - p0)) * (bottom - top);
  const step = priceStep(p1 - p0, (bottom - top) * s);
  const digits = step < 0.01 ? 5 : step < 0.5 ? 2 : 1;
  const grid: number[] = [];
  for (let p = Math.ceil(p0 / step) * step; p <= p1 + 1e-9; p += step) grid.push(p);
  const f = (v: number) => v.toFixed(1);
  // Agent overlays: read-only, in the chart's own colours (Q37).
  const lines: Line[] = [];
  const segments: Segment[] = [];
  const timeX = (iso: unknown) => {
    const ms = Date.parse(String(iso));
    if (!bars.length || !Number.isFinite(ms)) return null;
    const span = bars.length > 1 ? (bars.at(-1)!.t - bars[0].t) / (bars.length - 1) : 1;
    return X(0) + ((ms - bars[0].t) / (span || 1)) * 17 + 5;
  };
  for (const item of scene?.annotations ?? []) {
    const kind = String(item.type);
    if (["price", "horizontal_line", "note"].includes(kind) && item.price != null) {
      const y = Y(num(item.price));
      if (y >= top && y <= bottom)
        lines.push({ y, label: typeof item.label === "string" ? item.label : undefined });
    } else if (item.start && item.end) {
      const a = item.start as { time: unknown; price: unknown };
      const b = item.end as { time: unknown; price: unknown };
      const x1 = timeX(a.time);
      const x2 = timeX(b.time);
      if (x1 != null && x2 != null)
        segments.push({ x1, y1: Y(num(a.price)), x2, y2: Y(num(b.price)) });
    }
  }
  const series: string[] = [];
  if (scene && scene.timeframe === frame && scene.candles.length) {
    const times = scene.candles.map((c) => Date.parse(c.time));
    for (const indicator of scene.indicators) {
      for (const values of Object.values(indicator.series)) {
        const points = bars
          .map((bar, i) => {
            const at = times.indexOf(bar.t);
            const value = at < 0 ? null : values[at];
            return value == null ? null : `${f(X(i) + 5)},${f(Y(value))}`;
          })
          .filter(Boolean);
        if (points.length > 1) series.push(points.join(" "));
      }
    }
  }
  return (
    <svg
      ref={ref}
      className="chart grow"
      viewBox={`0 0 ${VW} ${VH}`}
      role="img"
      aria-label={t`Market chart`}
    >
      {grid.map((p) => (
        <g key={p}>
          <path
            d={`M15 ${f(Y(p))}H${right}`}
            style={{ stroke: "var(--line)" }}
            strokeDasharray="4 5"
          />
          <text
            x={right + 8}
            y={f(Y(p) + fs * 0.35)}
            style={{ fill: "var(--muted)" }}
            fontSize={fs}
          >
            {p.toFixed(digits)}
          </text>
        </g>
      ))}
      {bars.map((bar, i) => {
        const x = X(i);
        const color = bar.c >= bar.o ? "var(--mint)" : "var(--red)";
        const y = Y(Math.max(bar.o, bar.c));
        const h = Math.max(3, Math.abs(Y(bar.o) - Y(bar.c)));
        return (
          <g key={bar.t}>
            <line
              x1={f(x + 5)}
              x2={f(x + 5)}
              y1={f(Y(bar.h))}
              y2={f(Y(bar.l))}
              style={{ stroke: color }}
            />
            <rect x={f(x)} y={f(y)} width="10" height={f(h)} rx="1.5" style={{ fill: color }} />
          </g>
        );
      })}
      {series.map((points) => (
        <polyline
          key={points}
          points={points}
          fill="none"
          style={{ stroke: "var(--accent)" }}
          strokeWidth="1.5"
        />
      ))}
      {lines.map((line) => (
        <g key={`${line.y}-${line.label ?? ""}`} data-overlay="line">
          <path
            d={`M15 ${f(line.y)}H${right}`}
            style={{ stroke: "var(--amber)" }}
            strokeDasharray="6 4"
          />
          {line.label && (
            <text x={18} y={f(line.y - fs * 0.4)} style={{ fill: "var(--amber)" }} fontSize={fs}>
              {line.label}
            </text>
          )}
        </g>
      ))}
      {segments.map((seg) => (
        <line
          key={`${seg.x1}-${seg.y1}-${seg.x2}-${seg.y2}`}
          data-overlay="segment"
          x1={f(seg.x1)}
          y1={f(seg.y1)}
          x2={f(seg.x2)}
          y2={f(seg.y2)}
          style={{ stroke: "var(--amber)" }}
          strokeWidth="1.5"
        />
      ))}
      {bars.map((bar, i) =>
        (bars.length - 1 - i) % 7 === 1 && X(i) >= 15 ? (
          <text
            key={`t${bar.t}`}
            x={f(X(i))}
            y={f(VH - fs * 0.6)}
            style={{ fill: "var(--muted)" }}
            fontSize={fs}
          >
            {hm(bar.t)}
          </text>
        ) : null,
      )}
    </svg>
  );
}

/* The chart sheet (l_chart, Q37): the reference's look with the broker's candles for the
   agent's pair, the timeframe tabs and the expandable sheet; the agent's annotations and
   indicators from its chart (charts resource) as read-only overlays. */
export function ChartSheetBody({
  accountId,
  symbol,
  agentId,
  preferredChartId,
  initialFrame,
}: {
  accountId: string;
  symbol: string;
  agentId?: string;
  preferredChartId?: string;
  /** A chart opened by its id starts on its own timeframe. */
  initialFrame?: string;
}) {
  const { revision } = useClient();
  const [frame, setFrame] = useState<Frame>(FRAMES.find((item) => item === initialFrame) ?? "5m");
  const [candles, setCandles] = useState<Candle[] | null>(null);
  const [scene, setScene] = useState<ChartScene | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    let live = true;
    setCandles(null);
    setError(undefined);
    readCandles(accountId, symbol, frame)
      .then((rows) => live && setCandles(rows))
      .catch((failure: unknown) => live && setError(failure));
    return () => {
      live = false;
    };
  }, [accountId, symbol, frame]);
  useEffect(() => {
    void revision;
    let live = true;
    charts
      .list(agentId)
      .then((rows: Resource<ChartState>[]) => {
        const mine = rows.filter(
          (row) => row.payload.account_id === accountId && row.payload.symbol === symbol,
        );
        const pick = mine.find((row) => row.id === preferredChartId) ?? mine[0];
        return pick ? readScene(pick.id) : null;
      })
      .then((next) => live && setScene(next))
      .catch(() => live && setScene(null));
    return () => {
      live = false;
    };
  }, [accountId, symbol, agentId, preferredChartId, revision]);
  return (
    <div className="chart-body grow">
      <div className="tabs" role="tablist">
        {FRAMES.map((item) => (
          <button
            type="button"
            role="tab"
            key={item}
            aria-selected={frame === item}
            className={frame === item ? "active" : ""}
            onClick={() => setFrame(item)}
          >
            <span className="ltr">{item}</span>
          </button>
        ))}
      </div>
      {error != null ? (
        <p role="alert">{userError(error)}</p>
      ) : candles === null ? (
        <SkPage>
          <span className="sk sk-chart" style={{ display: "block", aspectRatio: "600 / 310" }} />
        </SkPage>
      ) : candles.length ? (
        <CandleChart candles={candles} scene={scene} frame={frame} />
      ) : (
        <p className="note">
          <Trans>No candles for this timeframe yet.</Trans>
        </p>
      )}
    </div>
  );
}

/** A chart an answer named, or the conversation's latest: its pair comes from the chart. */
function ChartById({
  chartId,
  agentId,
  threadId,
}: {
  chartId?: string;
  agentId?: string;
  threadId?: string;
}) {
  const [row, setRow] = useState<Resource<ChartState> | null | undefined>();
  useEffect(() => {
    let live = true;
    charts
      .list()
      .then((rows) => {
        const pick = chartId
          ? rows.find((item) => item.id === chartId)
          : rows.find(
              (item) =>
                (agentId && item.agent_id === agentId) ||
                (threadId && item.thread_id === threadId) ||
                (!item.agent_id && !item.thread_id),
            );
        if (live) setRow(pick ?? null);
      })
      .catch(() => live && setRow(null));
    return () => {
      live = false;
    };
  }, [chartId, agentId, threadId]);
  if (row === undefined)
    return (
      <SkPage>
        <span className="sk sk-chart" style={{ display: "block", aspectRatio: "600 / 310" }} />
      </SkPage>
    );
  if (!row)
    return (
      <p className="note">
        {chartId ? (
          <Trans>This chart is no longer available.</Trans>
        ) : (
          <Trans>
            This conversation has no pair to chart. Ask the agent for a chart, or open the market.
          </Trans>
        )}
      </p>
    );
  return (
    <ChartSheetBody
      accountId={row.payload.account_id}
      symbol={row.payload.symbol}
      agentId={agentId}
      preferredChartId={row.id}
      initialFrame={row.payload.timeframe}
    />
  );
}

/** Opens the chart sheet for a pair (the ⋮ menu «الشارت», a chart the answer asks for). */
export function useChartSheet() {
  const sheets = useSheets();
  return useCallback(
    (
      binding: { accountId: string; symbol: string } | null,
      options: { agentId?: string; chartId?: string; threadId?: string } = {},
    ) => {
      const pair = options.chartId ? null : binding;
      const title = pair ? (
        <>
          <Trans>Chart</Trans> <small className="ltr">{pair.symbol}</small>
        </>
      ) : (
        t`Chart`
      );
      sheets.open({
        id: "chart",
        expand: true,
        title,
        label: pair ? `${t`Chart`} ${pair.symbol}` : t`Chart`,
        body: pair ? (
          <ChartSheetBody
            key={`${pair.accountId}:${pair.symbol}`}
            accountId={pair.accountId}
            symbol={pair.symbol}
            agentId={options.agentId}
          />
        ) : (
          <ChartById
            chartId={options.chartId}
            agentId={options.agentId}
            threadId={options.threadId}
          />
        ),
      });
    },
    [sheets],
  );
}
