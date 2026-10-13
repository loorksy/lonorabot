import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useEvents } from "../hooks/useEvents";
import type { Owner } from "../lib/auth";

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
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useClient() {
  const value = useContext(Context);
  if (!value) throw new Error("client_context_missing");
  return value;
}
