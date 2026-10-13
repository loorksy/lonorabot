import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type Resource } from "../lib/api";
import { type ChartScene, type ChartState, charts, readScene, refreshChart } from "../lib/charts";
import { useClient } from "../providers/ClientProvider";

/** Reads resident chart state. Only an explicit owner action creates or changes a chart. */
export function useCharts(accountId: string, symbol: string) {
  const { events, connected } = useClient();
  const [rows, setRows] = useState<Resource<ChartState>[]>([]);
  const [selected, setSelected] = useState("");
  const [scene, setScene] = useState<ChartScene>();
  const [loading, setLoading] = useState(true);
  const [initializing, setInitializing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [refresh, setRefresh] = useState(0);
  const action = useRef(false);
  const loadedScope = useRef("");
  const selectedId = useRef("");
  selectedId.current = selected;
  const chartCursor = useRef(0);
  const entity = useRef(`${accountId}:${symbol}`);
  entity.current = `${accountId}:${symbol}`;
  const eventCursor = events.reduce(
    (cursor, event) =>
      event.kind.startsWith("cloud_charts.") ? Math.max(cursor, event.cursor) : cursor,
    chartCursor.current,
  );
  chartCursor.current = eventCursor;
  const row = rows.find((item) => item.id === selected);

  useEffect(() => {
    void connected;
    void eventCursor;
    void refresh;
    let live = true;
    const scope = `${accountId}:${symbol}`;
    if (loadedScope.current !== scope) setLoading(true);
    loadedScope.current = scope;
    void charts
      .list()
      .then((all) => {
        if (!live) return;
        const matching = all
          .filter(
            (item) =>
              item.payload.account_id === accountId &&
              (item.payload.symbol === symbol || item.id === selectedId.current),
          )
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
        setRows(matching);
        setSelected((id) =>
          matching.some((item) => item.id === id) ? id : (matching[0]?.id ?? ""),
        );
        setError(undefined);
      })
      .catch((caught: unknown) => {
        if (live) setError(caught);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [accountId, symbol, connected, eventCursor, refresh]);

  const id = row?.id;
  const version = row?.version;
  const sceneVersion = row?.state?.scene_version;
  useEffect(() => {
    void sceneVersion;
    void refresh;
    void connected;
    setScene((old) => (old && old.chart_id === id && old.revision === version ? old : undefined));
    if (!id) {
      setInitializing(false);
      return;
    }
    let live = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const until = Date.now() + 60_000;
    setInitializing(true);
    const load = () =>
      void readScene(id)
        .then((value) => {
          if (!live) return;
          setScene(value);
          setInitializing(false);
          setError(undefined);
        })
        .catch((caught: unknown) => {
          if (!live) return;
          if (caught instanceof ApiError && caught.code === "chart_initializing") {
            if (Date.now() < until) retry = setTimeout(load, 1000);
            else {
              setInitializing(false);
              setError(caught);
            }
            return;
          }
          setInitializing(false);
          setError(caught);
        });
    load();
    return () => {
      live = false;
      if (retry) clearTimeout(retry);
    };
  }, [id, version, sceneVersion, refresh, connected]);

  const act = useCallback(async (perform: () => Promise<void>) => {
    if (action.current) return;
    action.current = true;
    const current = entity.current;
    setBusy(true);
    setError(undefined);
    try {
      await perform();
    } catch (caught) {
      if (entity.current === current) setError(caught);
    } finally {
      action.current = false;
      if (entity.current === current) {
        setBusy(false);
        setRefresh((value) => value + 1);
      }
    }
  }, []);

  return {
    rows,
    row,
    scene,
    loading,
    initializing,
    busy,
    error,
    select: (id: string) => {
      setSelected(id);
      setError(undefined);
    },
    create: () =>
      act(async () => {
        const current = entity.current;
        const created = await charts.create({
          account_id: accountId,
          symbol,
          timeframe: "1h",
          indicators: [],
          annotations: [],
        });
        if (entity.current !== current) return;
        setRows((old) => [created, ...old]);
        setSelected(created.id);
      }),
    update: (payload: ChartState) =>
      act(async () => {
        if (!row) return;
        const current = entity.current;
        const updated = await charts.update(row, payload);
        if (entity.current === current)
          setRows((old) => old.map((item) => (item.id === updated.id ? updated : item)));
      }),
    refresh: () =>
      act(async () => {
        if (row) await refreshChart(row.id);
      }),
  };
}
