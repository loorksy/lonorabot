import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import type { Resource } from "../../lib/api";
import { type ChartScene, type ChartState, charts, readScene } from "../../lib/charts";
import { userError } from "../../lib/user_error";
import { ChartAnnotations } from "./ChartAnnotations";
import { ChartIndicators } from "./ChartIndicators";
import { ChartLiveFeed } from "./ChartLiveFeed";
import { ChartToolbar } from "./ChartToolbar";
import { TradingChart } from "./TradingChart";
export function ChartWorkspace({ accountId, symbol }: { accountId: string; symbol: string }) {
  const [row, setRow] = useState<Resource<ChartState>>();
  const [scene, setScene] = useState<ChartScene>();
  const [timeframe, setTimeframe] = useState("1h");
  const [live, setLive] = useState(false);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [error, setError] = useState<unknown>();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => setTick((v) => v + 1), 10000);
    return () => clearInterval(timer);
  }, [live]);
  useEffect(() => {
    setRow(undefined);
    setScene(undefined);
    if (!accountId || !symbol) return;
    let active = true;
    void charts
      .list()
      .then(async (rows) => {
        const found = rows.find(
          (c) =>
            c.payload.account_id === accountId &&
            c.payload.symbol === symbol &&
            c.payload.timeframe === timeframe,
        );
        const chart =
          found ??
          (await charts.create({
            account_id: accountId,
            symbol,
            timeframe,
            indicators: [],
            annotations: [],
          }));
        if (active) setRow(chart);
      })
      .catch(setError);
    return () => {
      active = false;
    };
  }, [accountId, symbol, timeframe]);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void tick;
    if (!row) return;
    let active = true;
    void readScene(row.id)
      .then((s) => {
        if (active) {
          setScene(s);
          setObservedAt(new Date().toISOString());
          setError(undefined);
        }
      })
      .catch((e) => {
        if (active) setError(e);
      });
    return () => {
      active = false;
    };
  }, [row, tick]);
  async function update(payload: ChartState) {
    if (!row) return;
    try {
      setRow(await charts.update(row, payload));
    } catch (e) {
      setError(e);
    }
  }
  return (
    <section className="card chart-workspace">
      <h2>
        <Trans>Shared chart workspace</Trans>
      </h2>
      <ChartToolbar
        timeframe={timeframe}
        onChange={setTimeframe}
        onRefresh={() => setTick((v) => v + 1)}
      />
      {error != null && <p role="alert">{userError(error)}</p>}
      {scene && scene.candles.length > 0 ? (
        <TradingChart scene={scene} />
      ) : (
        <div className="empty">
          <Trans>No candles available for this instrument and timeframe.</Trans>
        </div>
      )}
      {row && (
        <>
          <ChartIndicators
            indicators={row.payload.indicators}
            onChange={(items) => void update({ ...row.payload, indicators: items })}
          />
          <ChartAnnotations
            annotations={row.payload.annotations}
            onChange={(items) => void update({ ...row.payload, annotations: items })}
          />
        </>
      )}
      <ChartLiveFeed observedAt={observedAt} live={live} onToggle={() => setLive((v) => !v)} />
    </section>
  );
}
