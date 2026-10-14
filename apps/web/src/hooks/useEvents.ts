import { useCallback, useEffect, useRef, useState } from "react";
import type { Event, Run } from "../lib/api";
import { eventSocket } from "../lib/events";
import { accumulateStream, type LiveReplyStream, seedStream } from "../lib/response_streaming";

const MAX_LIVE_STREAMS = 64;
type State = { events: Event[]; streams: Record<string, LiveReplyStream>; revision: number };
function trimStreams(streams: Record<string, LiveReplyStream>) {
  return Object.fromEntries(
    Object.entries(streams)
      .sort((a, b) => b[1].cursor - a[1].cursor)
      .slice(0, MAX_LIVE_STREAMS),
  );
}
export function useEvents(enabled: boolean) {
  const [state, setState] = useState<State>({ events: [], streams: {}, revision: 0 });
  const [connected, setConnected] = useState(false);
  const cursor = useRef(0);
  const seedStreams = useCallback((runs: Run[]) => {
    setState((old) => {
      const streams = { ...old.streams };
      for (const run of runs) {
        const seeded = seedStream(streams[run.id], run);
        if (seeded) streams[run.id] = seeded;
      }
      return { ...old, streams: trimStreams(streams) };
    });
  }, []);
  useEffect(() => {
    if (!enabled) {
      setState({ events: [], streams: {}, revision: 0 });
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
          setState((old) => {
            const stream = accumulateStream(
              event.run_id ? old.streams[event.run_id] : undefined,
              event,
            );
            return {
              events: [...old.events, event].slice(-150),
              streams: stream
                ? trimStreams({ ...old.streams, [stream.run_id]: stream })
                : old.streams,
              revision: [
                "run.delta",
                "run.reply_started",
                "run.progress",
                "market.quote_updated",
                "cloud_charts.scene_updated",
              ].includes(event.kind)
                ? old.revision
                : event.cursor,
            };
          });
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
  return { ...state, seedStreams, connected, cursor: cursor.current };
}
