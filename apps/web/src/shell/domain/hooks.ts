import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { Agent } from "../../lib/api";
import { useClient } from "../../providers/ClientProvider";
import { useShellData } from "../data";

/** The page's agent: `?agent=`, else the first agent (the reference's A()). */
export function useAgentParam(): Agent | undefined {
  const data = useShellData();
  const [params] = useSearchParams();
  const id = params.get("agent");
  return data.agents.find((agent) => agent.id === id) ?? data.agents[0];
}

export const useItemParam = () => useSearchParams()[0].get("item");

/** A trading agent: made from the trading template or bound to a pair or an account. */
export const isTrader = (agent: Agent | undefined) =>
  !!agent && (agent.template === "trading" || !!agent.trading_symbol || !!agent.trading_account_id);

export type Loaded<T> = {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  set: (update: (value: T | undefined) => T | undefined) => void;
};

/** Server data for a page, refetched when the event stream moves the client revision. */
export function useLoad<T>(load: (() => Promise<T>) | null, key: string): Loaded<T> {
  const { revision } = useClient();
  const [data, setData] = useState<T>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const [manual, setManual] = useState(0);
  // Another item: drop the previous one's data and error before the new load.
  const [loadedKey, setLoadedKey] = useState(key);
  if (loadedKey !== key) {
    setLoadedKey(key);
    setData(undefined);
    setError(undefined);
    setLoading(true);
  }
  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` names the query; `load` is recreated each render.
  useEffect(() => {
    void revision;
    void manual;
    if (!load) {
      setLoading(false);
      return;
    }
    let active = true;
    load()
      .then((value) => {
        if (!active) return;
        setData(value);
        setError(undefined);
      })
      .catch((cause) => {
        if (active) setError(cause);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [key, revision, manual]);
  const reload = useCallback(() => setManual((value) => value + 1), []);
  return { data, error, loading, reload, set: setData };
}
