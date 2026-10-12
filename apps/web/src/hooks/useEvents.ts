import { useEffect, useRef, useState } from "react";
import type { Event } from "../lib/api";
import { eventSocket } from "../lib/events";
export function useEvents(enabled: boolean) {
  const [events, setEvents] = useState<Event[]>([]);
  const [connected, setConnected] = useState(false);
  const cursor = useRef(0);
  useEffect(() => {
    if (!enabled) {
      setEvents([]);
      cursor.current = 0;
      return;
    }
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let socket: WebSocket;
    const connect = () => {
      socket = eventSocket(
        cursor.current,
        (event) => {
          if (event.cursor <= cursor.current) return;
          cursor.current = event.cursor;
          setEvents((old) => [...old, event].slice(-150));
        },
        () => {
          setConnected(false);
          if (!stopped) timer = setTimeout(connect, 2000);
        },
      );
      socket.addEventListener("open", () => setConnected(true));
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
      setConnected(false);
    };
  }, [enabled]);
  return { events, connected, cursor: cursor.current };
}
