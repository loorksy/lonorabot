import type { Candle, Quote, Resource } from "@lonora/contracts";
import { api } from "./api";
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
