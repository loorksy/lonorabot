import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useEvents } from "../hooks/useEvents";
import type { Owner } from "../lib/auth";

type Client = {
  owner: Owner;
  events: ReturnType<typeof useEvents>["events"];
  connected: boolean;
  revision: number;
  refresh: () => void;
};
const Context = createContext<Client | null>(null);
export function ClientProvider({ owner, children }: { owner: Owner; children: ReactNode }) {
  const { events, connected } = useEvents(true);
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
      connected,
      revision:
        manual +
        tick +
        ([...events]
          .reverse()
          .find((event) => !["run.delta", "run.reply_started", "run.progress"].includes(event.kind))
          ?.cursor ?? 0),
      refresh: () => setManual((v) => v + 1),
    }),
    [owner, events, connected, manual, tick],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useClient() {
  const value = useContext(Context);
  if (!value) throw new Error("client_context_missing");
  return value;
}
