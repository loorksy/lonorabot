import type { Event as RuntimeEvent } from "./api";

export type EventConnection = { close: () => void };

function validEvent(value: unknown): value is RuntimeEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<RuntimeEvent>;
  return (
    Number.isSafeInteger(event.cursor) &&
    Number(event.cursor) > 0 &&
    typeof event.kind === "string" &&
    !!event.kind &&
    !!event.payload &&
    typeof event.payload === "object" &&
    !Array.isArray(event.payload)
  );
}

/** One resumable HTTP stream. A ready baseline precedes canonical refresh. */
export function eventStream(
  initialCursor: number,
  onEvent: (event: RuntimeEvent) => void,
  onConnection: (connected: boolean) => void,
): EventConnection {
  let cursor = initialCursor;
  let initialized = initialCursor > 0;
  let stopped = false;
  let retry = 0;
  let source: EventSource | undefined;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let startupTimer: ReturnType<typeof setTimeout> | undefined;

  const clearTimers = () => {
    clearTimeout(reconnectTimer);
    clearTimeout(startupTimer);
  };
  const connect = () => {
    if (stopped) return;
    clearTimers();
    source?.close();
    const current = new EventSource(
      `/api/events/stream?cursor=${cursor}${initialized ? "" : "&live=true"}`,
      { withCredentials: true },
    );
    source = current;
    const active = () => !stopped && source === current;
    const reconnect = () => {
      if (!active()) return;
      current.close();
      clearTimers();
      onConnection(false);
      const delay = Math.min(10_000, 500 * 2 ** Math.min(retry++, 5));
      reconnectTimer = setTimeout(connect, delay);
    };
    // A buffering intermediary must not leave an apparently open but silent
    // connection indefinitely. The server flushes its ready frame immediately.
    startupTimer = setTimeout(reconnect, 10_000);
    current.addEventListener("ready", (message) => {
      if (!active()) return;
      try {
        const value = JSON.parse((message as MessageEvent<string>).data) as { cursor?: unknown };
        if (!Number.isSafeInteger(value.cursor) || Number(value.cursor) < cursor) return;
        cursor = Number(value.cursor);
        initialized = true;
        retry = 0;
        clearTimeout(startupTimer);
        onConnection(true);
      } catch {
        // A malformed frame cannot move the replay cursor or invalidate history.
      }
    });
    current.onmessage = (message) => {
      if (!active() || !initialized) return;
      try {
        const event: unknown = JSON.parse(message.data);
        if (!validEvent(event) || event.cursor <= cursor) return;
        cursor = event.cursor;
        onEvent(event);
      } catch {
        // Ignore incomplete/unrecognized data without dropping the live stream.
      }
    };
    current.onerror = reconnect;
  };
  const resume = () => {
    if (!stopped && source?.readyState !== EventSource.OPEN) connect();
  };
  const visible = () => {
    if (document.visibilityState === "visible") resume();
  };
  const close = () => {
    if (stopped) return;
    stopped = true;
    clearTimers();
    source?.close();
    window.removeEventListener("online", resume);
    window.removeEventListener("pageshow", resume);
    window.removeEventListener("lonora:session-reset", close);
    document.removeEventListener("visibilitychange", visible);
    onConnection(false);
  };
  window.addEventListener("online", resume);
  window.addEventListener("pageshow", resume);
  window.addEventListener("lonora:session-reset", close);
  document.addEventListener("visibilitychange", visible);
  connect();
  return { close };
}
