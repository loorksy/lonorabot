import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useEvents } from "../hooks/useEvents";
import type { Owner } from "../lib/auth";
import { AttentionProvider } from "./AttentionProvider";

type Client = {
  owner: Owner;
  events: ReturnType<typeof useEvents>["events"];
  streams: ReturnType<typeof useEvents>["streams"];
  seedStreams: ReturnType<typeof useEvents>["seedStreams"];
  connected: boolean;
  revision: number;
  refresh: () => void;
};
const Context = createContext<Client | null>(null);
export function ClientProvider({ owner, children }: { owner: Owner; children: ReactNode }) {
  const { events, streams, seedStreams, connected, revision } = useEvents(true);
  const [manual, setManual] = useState(0);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((v) => v + 1), 15000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (connected) setManual((value) => value + 1);
  }, [connected]);
  useEffect(() => {
    const reconcile = () => {
      if (document.visibilityState === "visible") setManual((value) => value + 1);
    };
    document.addEventListener("visibilitychange", reconcile);
    window.addEventListener("online", reconcile);
    return () => {
      document.removeEventListener("visibilitychange", reconcile);
      window.removeEventListener("online", reconcile);
    };
  }, []);
  const value = useMemo(
    () => ({
      owner,
      events,
      streams,
      seedStreams,
      connected,
      revision: manual + tick + revision,
      refresh: () => setManual((v) => v + 1),
    }),
    [owner, events, streams, seedStreams, connected, manual, tick, revision],
  );
  return (
    <Context.Provider value={value}>
      <AttentionProvider key={owner.id} revision={value.revision}>
        {children}
      </AttentionProvider>
    </Context.Provider>
  );
}
export function useClient() {
  const value = useContext(Context);
  if (!value) throw new Error("client_context_missing");
  return value;
}
