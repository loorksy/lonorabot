import { expect, test } from "@playwright/test";
import { chartResolution, SceneDatafeed } from "../../apps/web/src/lib/tradingview-feed.ts";

for (const [symbol, timeframe] of [
  ["EURUSD.raw", "1m"],
  ["XAUUSDm", "15m"],
  ["US500.cash", "4h"],
  ["BTCUSD#", "1mn"],
]) {
  test(`live official bars preserve ${symbol}/${timeframe} and roll without a reset`, () => {
    const scene = {
      chart_id: "live-fixture",
      revision: 1,
      scene_version: 1,
      symbol,
      timeframe,
      candles: Array.from({ length: 4 }, (_, i) => ({
        time: new Date(Date.UTC(2026, 0, i + 1)).toISOString(),
        open: 100,
        high: 105,
        low: 95,
        close: 101,
      })),
    };
    const feed = new SceneDatafeed(scene);
    const updates = [];
    let resets = 0;
    feed.onCorrection = async () => {
      resets++;
    };
    feed.api.subscribeBars(
      { ticker: symbol },
      chartResolution(timeframe),
      (bar) => updates.push(bar),
      "owner-chart",
      () => {},
    );
    const next = structuredClone(scene);
    next.scene_version++;
    next.candles.at(-1).close = 104;
    feed.update(next);
    expect(updates.map((bar) => bar.close)).toEqual([104]);
    expect(resets).toBe(0);

    // A price-only scene cannot change official OHLC or fabricate a new bar.
    updates.length = 0;
    feed.update({ ...next, scene_version: 3, quote: { bid: 110, ask: 111 } });
    expect(updates).toEqual([]);

    const rolling = structuredClone(next);
    rolling.scene_version = 4;
    rolling.candles.shift();
    rolling.candles.push({
      ...rolling.candles.at(-1),
      time: new Date(Date.UTC(2026, 0, 5)).toISOString(),
      close: 102,
    });
    feed.update(rolling);
    expect(updates.map((bar) => bar.close)).toEqual([102]);
    expect(resets).toBe(0);
    expect(feed.scene.symbol).toBe(symbol);
    expect(feed.scene.timeframe).toBe(timeframe);

    const correction = structuredClone(rolling);
    correction.candles[1].high = 106;
    feed.update(correction);
    expect(resets).toBe(1);
    expect(updates).toHaveLength(1);

    const inserted = structuredClone(correction);
    inserted.candles.splice(1, 0, {
      ...inserted.candles[0],
      time: new Date(Date.UTC(2026, 0, 2, 12)).toISOString(),
    });
    feed.update(inserted);
    expect(resets).toBe(2);
    feed.api.unsubscribeBars("owner-chart");
    const afterClose = structuredClone(inserted);
    afterClose.candles.at(-1).close = 103;
    feed.update(afterClose);
    expect(updates).toHaveLength(1);
  });
}
