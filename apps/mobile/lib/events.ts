/** Existing authenticated durable owner stream, shared by charts and conversation adapters. */
import type { Event } from "@lonora/contracts";
import { AppState, Platform } from "react-native";
import { registerSessionTeardown } from "./session-lifecycle";
import { loadNativeToken } from "./storage";
export type EventConnection = "connecting" | "connected" | "reconnecting";
const closers = new Set<() => void>();
registerSessionTeardown(async () => {
  for (const close of [...closers]) close();
});
export function subscribeOwnerEvents(
  server: string,
  onEvent: (event: Event) => void,
  onReconnect: () => void,
  onConnection: (state: EventConnection) => void = () => undefined,
): () => void {
  let stopped = false,
    cursor = 0,
    connected = false,
    initialized = false;
  let foreground = AppState.currentState !== "background" && AppState.currentState !== "inactive";
  let readiness: ReturnType<typeof setTimeout> | undefined;
  let socket: WebSocket | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const connect = () => {
    if (stopped || !foreground) return;
    onConnection(connected ? "reconnecting" : "connecting");
    const url = new URL(`${server}/api/ws/events`);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const current = new WebSocket(url.toString());
    socket = current;
    readiness = setTimeout(() => current.close(), 10000);
    current.onopen = () => {
      void (async () => {
        const token = Platform.OS === "web" ? null : await loadNativeToken();
        if (stopped || socket !== current || current.readyState !== WebSocket.OPEN) return;
        if (Platform.OS !== "web" && !token) {
          current.close();
          return;
        }
        current.send(
          JSON.stringify({
            cursor,
            ...(!initialized ? { live: true } : {}),
            ...(token ? { token } : {}),
          }),
        );
      })().catch(() => current.close());
    };
    current.onmessage = (message) => {
      if (stopped || socket !== current) return;
      try {
        const value = JSON.parse(String(message.data));
        if (
          value?.type === "ready" &&
          Number.isSafeInteger(value.cursor) &&
          value.cursor >= cursor
        ) {
          cursor = value.cursor;
          initialized = true;
          connected = true;
          if (readiness) clearTimeout(readiness);
          onConnection("connected");
          onReconnect();
          return;
        }
        if (!initialized) return;
        const event = value as Event;
        if (
          !Number.isSafeInteger(event.cursor) ||
          event.cursor <= cursor ||
          typeof event.kind !== "string" ||
          !event.payload ||
          typeof event.payload !== "object"
        )
          return;
        onEvent(event);
        cursor = event.cursor;
      } catch {
        current.close(); /* Resume from the last consumed durable event. */
      }
    };
    current.onerror = () => current.close();
    current.onclose = () => {
      if (readiness) clearTimeout(readiness);
      if (!stopped && foreground && socket === current) {
        onConnection("reconnecting");
        timer = setTimeout(connect, 1500);
      }
    };
  };
  const subscription = AppState.addEventListener("change", (state) => {
    foreground = state === "active";
    if (!foreground) {
      if (timer) clearTimeout(timer);
      socket?.close();
    } else if (
      !stopped &&
      socket?.readyState !== WebSocket.OPEN &&
      socket?.readyState !== WebSocket.CONNECTING
    )
      connect();
  });
  const close = () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    if (readiness) clearTimeout(readiness);
    socket?.close();
    subscription.remove();
    closers.delete(close);
  };
  closers.add(close);
  connect();
  return close;
}
