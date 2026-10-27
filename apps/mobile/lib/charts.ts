import type { Candle, Quote, Resource } from "@lonora/contracts";
import { api } from "./api";

// Preserve the official SDK's monthly spelling and all 21 canonical MT5 intervals.
export const CHART_TIMEFRAMES = [
  "1m",
  "2m",
  "3m",
  "4m",
  "5m",
  "6m",
  "10m",
  "12m",
  "15m",
  "20m",
  "30m",
  "1h",
  "2h",
  "3h",
  "4h",
  "6h",
  "8h",
  "12h",
  "1d",
  "1w",
  "1mn",
] as const;
export type ChartState = {
  account_id: string;
  symbol: string;
  timeframe: string;
  indicators: { name: string; period: number }[];
  annotations: Record<string, unknown>[];
};
export type Chart = Resource<ChartState>;
export type ChartScene = {
  chart_id: string;
  revision: number;
  scene_version: number;
  data_revision?: string;
  candle_observed_at?: string | null;
  observation_source?: string;
  status: "ready";
  updated_at: string;
  symbol: string;
  timeframe: string;
  candles: Candle[];
  quote?: Quote | null;
  indicators: { name: string; period: number; series: Record<string, (number | null)[]> }[];
  annotations: Record<string, unknown>[];
};
export const readCharts = (threadId?: string) =>
  api.get<Chart[]>(`/charts${threadId ? `?thread_id=${encodeURIComponent(threadId)}` : ""}`);
export const readScene = (id: string) =>
  api.get<ChartScene>(`/charts/${encodeURIComponent(id)}/scene`);
export const requestRefresh = (id: string) =>
  api.post<{ requested: boolean }>(`/charts/${encodeURIComponent(id)}/refresh`, {});

export { subscribeOwnerEvents as subscribeChartEvents } from "./events";
