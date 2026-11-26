/** Existing authenticated durable owner stream, shared by charts and conversation adapters. */
import type { Event } from "@lonora/contracts";
import { addNetworkStateListener, getNetworkStateAsync, type NetworkState } from "expo-network";
import { AppState, Platform } from "react-native";
import { registerSessionTeardown } from "./session-lifecycle";
import { loadNativeToken } from "./storage";
export type EventConnection = "connecting" | "connected" | "reconnecting";
// The server sends a frame (an event or a ping) at least every 15 s. A socket that carries none
// for this long is dead even when it still looks open (a half-open socket after a network change).
const IDLE_MS = 45_000;
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
  let silence: ReturnType<typeof setTimeout> | undefined;
  let socket: WebSocket | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  // Leave a socket at once and connect again: a half-open socket may report its close only after
  // a minute, and a late close of a socket already left changes nothing.
  const replace = (current: WebSocket) => {
    if (socket !== current) return;
    socket = undefined;
    if (silence) clearTimeout(silence);
    current.close();
    if (!stopped && foreground) {
      onConnection("reconnecting");
      timer = setTimeout(connect, 1500);
    }
  };
  const connect = () => {
    if (stopped || !foreground) return;
    onConnection(connected ? "reconnecting" : "connecting");
    const url = new URL(`${server}/api/ws/events`);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const current = new WebSocket(url.toString());
    socket = current;
    let live = false;
    const expectFrameWithin = (ms: number) => {
      if (silence) clearTimeout(silence);
      silence = setTimeout(() => replace(current), ms);
    };
    expectFrameWithin(10000);
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
      if (live) expectFrameWithin(IDLE_MS);
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
          live = true;
          expectFrameWithin(IDLE_MS);
          onConnection("connected");
          onReconnect();
          return;
        }
        // A ping has no cursor: it only re-armed the silence timer and is never an event.
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
    current.onclose = () => replace(current);
  };
  // A network change (Wi-Fi to mobile data, offline and back) leaves the socket half-open, so it
  // is replaced at once instead of after the silence timeout. A repeated reading changes nothing.
  let network: string | undefined;
  const networkChanged = (state: NetworkState) => {
    const next = `${state.type}/${state.isConnected}`;
    const changed = network !== undefined && next !== network;
    network = next;
    return changed;
  };
  void getNetworkStateAsync().then(networkChanged, () => undefined);
  const networkSubscription = addNetworkStateListener((state) => {
    if (networkChanged(state) && socket) replace(socket);
  });
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
    if (silence) clearTimeout(silence);
    socket?.close();
    subscription.remove();
    networkSubscription.remove();
    closers.delete(close);
  };
  closers.add(close);
  connect();
  return close;
}
