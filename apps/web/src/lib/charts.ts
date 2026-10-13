import { api, type Candle, type Quote } from "./api";
import { resources } from "./rpc";
export type ChartState = {
  account_id: string;
  symbol: string;
  timeframe: string;
  indicators: { name: string; period: number }[];
  annotations: Record<string, unknown>[];
};
export type ChartScene = {
  chart_id: string;
  revision: number;
  scene_version: number;
  status: "ready" | "failed" | "initializing";
  updated_at: string;
  error_code?: string | null;
  quote?: Quote | null;
  symbol: string;
  timeframe: string;
  candles: Candle[];
  indicators: { name: string; period: number; series: Record<string, (number | null)[]> }[];
  annotations: Record<string, unknown>[];
};
export const charts = resources<ChartState>("/charts");
export const readScene = (id: string) => api.get<ChartScene>(`/charts/${id}/scene`);
export const refreshChart = (id: string) =>
  api.post<{ refreshed: boolean }>(`/charts/${id}/refresh`, {});
