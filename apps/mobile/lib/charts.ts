import type { Candle, Event, Quote, Resource } from "@lonora/contracts";
import { Platform } from "react-native";
import { api } from "./api";
import { loadNativeToken } from "./storage";

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

/** Resume the existing durable owner stream; native credentials stay out of URLs. */
export function subscribeChartEvents(
  server: string,
  onEvent: (event: Event) => void,
  onReconnect: () => void,
): () => void {
  let stopped = false;
  let cursor = 0;
  let socket: WebSocket | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const connect = () => {
    if (stopped) return;
    const url = new URL(`${server}/api/ws/events`);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const current = new WebSocket(url.toString());
    socket = current;
    current.onopen = () => {
      void (async () => {
        const token = Platform.OS === "web" ? null : await loadNativeToken();
        if (stopped || socket !== current || current.readyState !== WebSocket.OPEN) return;
        if (Platform.OS !== "web" && !token) {
          current.close();
          return;
        }
        current.send(JSON.stringify(token ? { cursor, token } : { cursor }));
        onReconnect();
      })().catch(() => current.close());
    };
    current.onmessage = (message) => {
      if (stopped || current !== socket) return;
      try {
        const event = JSON.parse(String(message.data)) as Event;
        if (!Number.isSafeInteger(event.cursor) || event.cursor <= cursor) return;
        cursor = event.cursor;
        if (typeof event.kind === "string" && event.payload && typeof event.payload === "object")
          onEvent(event);
      } catch {
        // The next durable event or reconnect resumes from the last accepted cursor.
      }
    };
    current.onerror = () => current.close();
    current.onclose = () => {
      if (!stopped && current === socket) timer = setTimeout(connect, 2000);
    };
  };
  connect();
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    socket?.close();
  };
}
