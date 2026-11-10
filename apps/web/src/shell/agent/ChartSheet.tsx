import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { Candle, Resource } from "../../lib/api";
import { type ChartScene, type ChartState, charts, readScene } from "../../lib/charts";
import { readCandles } from "../../lib/market";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { SkPage } from "../Skeleton";
import { useSheets } from "../sheets/SheetHost";
import { layout } from "./chart-geometry";
import "./agent.css";

const FRAMES = ["5m", "15m", "1h", "4h"] as const;
type Frame = (typeof FRAMES)[number];

type Size = { w: number; h: number };
const TONE = { agent: "var(--amber)", up: "var(--mint)", down: "var(--red)" } as const;
/** How often an open chart re-reads its candles (the broker's own cadence is finer). */
const POLL_MS = 15_000;
const f = (v: number) => v.toFixed(1);

/* The reference's look (chartGeom/drawChart) over the broker's candles; the agent's drawings
   and indicators are read-only, each kind in its own form (chart-geometry.ts). */
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
  const sameFrame = Boolean(scene && scene.timeframe === frame);
  const g = layout({
    width: size.w,
    height: size.h,
    frame,
    bars: candles.map((c) => ({
      t: Date.parse(c.time),
      o: Number(c.open),
      h: Number(c.high),
      l: Number(c.low),
      c: Number(c.close),
    })),
    annotations: scene?.annotations ?? [],
    indicators: sameFrame && scene ? scene.indicators : [],
    indicatorTimes: sameFrame && scene ? scene.candles.map((c) => Date.parse(c.time)) : [],
    labels: {
      entry: t({ message: "Entry", context: "chart" }),
      stop: t({ message: "Stop", context: "chart" }),
      target: t({ message: "Target", context: "chart" }),
    },
  });
  const { fs, right } = g;
  // Everything on the price scale stays in the price area, out of the oscillator panes.
  const clip = `ag-plot-${useId().replace(/:/g, "")}`;
  return (
    <svg
      ref={ref}
      className="chart grow"
      viewBox={`0 0 ${g.VW} ${g.VH}`}
      role="img"
      aria-label={t`Market chart`}
    >
      <defs>
        <clipPath id={clip}>
          <rect x={f(g.plot.x)} y={f(g.plot.y)} width={f(g.plot.w)} height={f(g.plot.h)} />
        </clipPath>
      </defs>
      {g.grid.map((line) => (
        <g key={line.label}>
          <path
            d={`M15 ${f(line.y)}H${right}`}
            style={{ stroke: "var(--line)" }}
            strokeDasharray="4 5"
          />
          <text
            x={right + 8}
            y={f(line.y + fs * 0.35)}
            style={{ fill: "var(--muted)" }}
            fontSize={fs}
          >
            {line.label}
          </text>
        </g>
      ))}
      <g clipPath={`url(#${clip})`}>
        {g.shapes.map((shape, index) =>
          shape.kind === "box" ? (
            // biome-ignore lint/suspicious/noArrayIndexKey: drawings have no stable key here
            <g key={index} data-overlay="zone">
              <rect
                x={f(shape.x)}
                y={f(shape.y)}
                width={f(shape.w)}
                height={f(shape.h)}
                style={{ fill: TONE[shape.tone], fillOpacity: 0.14, stroke: TONE[shape.tone] }}
              />
              {shape.label && (
                <text
                  x={f(shape.lx)}
                  y={f(shape.y + fs)}
                  style={{ fill: TONE[shape.tone] }}
                  fontSize={fs}
                >
                  {shape.label}
                </text>
              )}
            </g>
          ) : null,
        )}
      </g>
      {g.bars.map((bar, i) => {
        const x = g.X(i);
        const color = bar.c >= bar.o ? "var(--mint)" : "var(--red)";
        const y = g.Y(Math.max(bar.o, bar.c));
        const h = Math.max(3, Math.abs(g.Y(bar.o) - g.Y(bar.c)));
        return (
          <g key={bar.t}>
            <line
              x1={f(x + 5)}
              x2={f(x + 5)}
              y1={f(g.Y(bar.h))}
              y2={f(g.Y(bar.l))}
              style={{ stroke: color }}
            />
            <rect x={f(x)} y={f(y)} width="10" height={f(h)} rx="1.5" style={{ fill: color }} />
          </g>
        );
      })}
      <g clipPath={`url(#${clip})`}>
        {g.priceLines.map((line) => (
          <polyline
            key={line.name}
            data-overlay="indicator"
            points={line.points}
            fill="none"
            style={{ stroke: "var(--accent)" }}
            strokeWidth="1.5"
          />
        ))}
        {g.shapes.map((shape, index) => {
          if (shape.kind === "hline")
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: drawings have no stable key here
              <g key={index} data-overlay="line">
                <path
                  d={`M${f(shape.x1)} ${f(shape.y)}H${f(shape.x2)}`}
                  style={{ stroke: TONE[shape.tone] }}
                  strokeDasharray={shape.dash ? "6 4" : undefined}
                />
                {shape.label && (
                  <text
                    x={f(shape.x1 + 3)}
                    y={f(shape.y - fs * 0.4)}
                    style={{ fill: TONE[shape.tone] }}
                    fontSize={fs}
                  >
                    {shape.label}
                  </text>
                )}
              </g>
            );
          if (shape.kind === "segment")
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: drawings have no stable key here
              <g key={index} data-overlay={shape.arrow ? "arrow" : "segment"}>
                <line
                  x1={f(shape.x1)}
                  y1={f(shape.y1)}
                  x2={f(shape.x2)}
                  y2={f(shape.y2)}
                  style={{ stroke: TONE[shape.tone] }}
                  strokeWidth="1.5"
                />
                {shape.arrow && (
                  <circle
                    cx={f(shape.x2)}
                    cy={f(shape.y2)}
                    r={3}
                    style={{ fill: TONE[shape.tone] }}
                  />
                )}
              </g>
            );
          if (shape.kind === "note")
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: drawings have no stable key here
              <g key={index} data-overlay="note">
                <circle
                  cx={f(shape.x)}
                  cy={f(shape.y)}
                  r={3.5}
                  style={{ fill: TONE[shape.tone] }}
                />
                {shape.text && (
                  <text
                    x={f(shape.tx)}
                    y={f(shape.y - fs * 0.6)}
                    textAnchor={shape.anchor}
                    style={{ fill: TONE[shape.tone] }}
                    fontSize={fs}
                  >
                    {shape.text}
                  </text>
                )}
              </g>
            );
          return null;
        })}
      </g>
      {g.panes.map((pane) => (
        <g key={pane.label} data-overlay="pane">
          <path d={`M15 ${f(pane.top - fs * 0.8)}H${right}`} style={{ stroke: "var(--line)" }} />
          <text x={18} y={f(pane.top + fs * 0.2)} style={{ fill: "var(--muted)" }} fontSize={fs}>
            {pane.more ? `${pane.label} · +${pane.more}` : pane.label}
          </text>
          {pane.guides.map((guide) => (
            <g key={guide.label}>
              <path
                d={`M15 ${f(guide.y)}H${right}`}
                style={{ stroke: "var(--line)" }}
                strokeDasharray="2 4"
              />
              <text
                x={right + 8}
                y={f(guide.y + fs * 0.35)}
                style={{ fill: "var(--muted)" }}
                fontSize={fs}
              >
                {guide.label}
              </text>
            </g>
          ))}
          {pane.lines.map((line) => (
            <polyline
              key={line.name}
              points={line.points}
              fill="none"
              style={{ stroke: "var(--accent)" }}
              strokeWidth="1.5"
            />
          ))}
        </g>
      ))}
      {g.times.map((time) => (
        <text
          key={time.x}
          x={f(time.x)}
          y={f(g.VH - fs * 0.6)}
          style={{ fill: "var(--muted)" }}
          fontSize={fs}
        >
          {time.label}
        </text>
      ))}
    </svg>
  );
}

/* The chart sheet (l_chart, Q37): the reference's look with the broker's candles for the
   pair, the timeframe tabs and the expandable sheet; the agent's annotations and indicators
   from the chart shown (charts resource) as read-only overlays. Candles are re-read while the
   sheet is open, and the scene again on every cloud_charts.scene_updated of that chart. */
export function ChartSheetBody({
  accountId,
  symbol,
  agentId,
  chartId,
  initialFrame,
}: {
  accountId: string;
  symbol: string;
  agentId?: string;
  /** The chart shown; without it, the agent's chart on this pair (if any). */
  chartId?: string;
  /** A chart opened by its id starts on its own timeframe. */
  initialFrame?: string;
}) {
  const { events } = useClient();
  const [frame, setFrame] = useState<Frame>(FRAMES.find((item) => item === initialFrame) ?? "5m");
  const [candles, setCandles] = useState<Candle[] | null>(null);
  const [scene, setScene] = useState<ChartScene | null>(null);
  const [chosen, setChosen] = useState<string | null | undefined>(chartId);
  const [error, setError] = useState<unknown>();
  // The chart named stays; otherwise the newest of the agent's charts on this pair
  // (chart_open always makes a new chart, even on the same pair). Re-listed only on the agent's
  // own chart events: a chart created or deleted, a listed chart updated (chart_set_symbol can
  // move it off this pair), or a scene for a chart this sheet has not listed, counted only for
  // events after the list was sent; never on every streamed scene update.
  const [listed, setListed] = useState<{ ids: ReadonlySet<string>; at: number } | null>(null);
  const latest = useRef(0);
  latest.current = events.at(-1)?.cursor ?? 0;
  const chartEvents = events
    .filter((event) => {
      if (agentId && event.agent_id !== agentId) return false;
      const id = typeof event.payload?.id === "string" ? event.payload.id : null;
      if (event.kind === "cloud_charts.created" || event.kind === "cloud_charts.deleted")
        return true;
      if (event.kind === "cloud_charts.updated") return id != null && !!listed?.ids.has(id);
      return (
        event.kind === "cloud_charts.scene_updated" &&
        id != null &&
        listed != null &&
        event.cursor > listed.at &&
        !listed.ids.has(id)
      );
    })
    .at(-1)?.cursor;
  useEffect(() => {
    void chartEvents;
    if (chartId) return;
    let live = true;
    const at = latest.current;
    charts
      .list(agentId)
      .then((rows: Resource<ChartState>[]) => {
        if (!live) return;
        setListed({ ids: new Set(rows.map((row) => row.id)), at });
        const mine = rows
          .filter((row) => row.payload.account_id === accountId && row.payload.symbol === symbol)
          .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
        setChosen(mine?.id ?? null);
        if (!mine) setScene(null);
      })
      .catch(() => live && setChosen(null));
    return () => {
      live = false;
    };
  }, [chartId, agentId, accountId, symbol, chartEvents]);
  const updated = events
    .filter((event) => event.kind === "cloud_charts.scene_updated" && event.payload?.id === chosen)
    .at(-1)?.cursor;
  useEffect(() => {
    void updated;
    if (!chosen) return;
    let live = true;
    readScene(chosen)
      .then((next) => live && setScene(next))
      .catch(() => live && setScene(null));
    return () => {
      live = false;
    };
  }, [chosen, updated]);
  useEffect(() => {
    let live = true;
    const read = () =>
      readCandles(accountId, symbol, frame)
        .then((rows) => {
          if (!live) return;
          setCandles(rows);
          setError(undefined);
        })
        .catch((failure: unknown) => live && setError(failure));
    void read();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void read();
    }, POLL_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [accountId, symbol, frame]);
  // A new timeframe starts from its skeleton, not the previous frame's bars.
  useEffect(() => {
    void frame;
    setCandles(null);
  }, [frame]);
  return (
    <div className="chart-body grow ag-scope" data-chart-id={chosen ?? undefined}>
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
      {error != null && !candles ? (
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
      chartId={row.id}
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
