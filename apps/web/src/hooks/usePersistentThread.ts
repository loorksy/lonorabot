import { useEffect, useState } from "react";
import { api, type Thread } from "../lib/api";
import { useClient } from "../providers/ClientProvider";

const pending = new Map<string, Promise<Thread[]>>();
function load(owner: string, agent: string) {
  const key = `${owner}:${agent}`;
  let promise = pending.get(key);
  if (!promise) {
    promise = api
      .get<Thread[]>(`/threads?agent_id=${agent}`)
      .then(async (rows) => {
        const direct = rows.filter((row) => !row.group_id);
        if (direct.length) return direct;
        return [await api.post<Thread>(`/agents/${agent}/conversation`, {})];
      })
      .finally(() => pending.delete(key));
    pending.set(key, promise);
  }
  return promise;
}
export function usePersistentThread(agent: string, requested?: string | null) {
  const { owner, revision } = useClient();
  const [state, setState] = useState<{ thread?: Thread; threads: Thread[]; error?: unknown }>({
    threads: [],
  });
  useEffect(() => {
    void agent;
    void owner.id;
    void requested;
    setState({ threads: [] });
  }, [agent, owner.id, requested]);
  useEffect(() => {
    void revision;
    let live = true;
    const key = `lonora:thread:${owner.id}:${agent}`;
    void load(owner.id, agent)
      .then((rows) => {
        if (!live) return;
        let saved: string | null = null;
        try {
          saved = localStorage.getItem(key);
        } catch {
          /* Optional preference. */
        }
        const thread =
          rows.find((row) => row.id === (requested || saved)) ??
          [...rows].sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
        if (requested && thread?.id !== requested) {
          setState({ threads: rows, error: { code: "not_found" } });
          return;
        }
        if (thread) {
          try {
            localStorage.setItem(key, thread.id);
          } catch {
            /* Optional preference. */
          }
        }
        setState({ threads: rows, thread });
      })
      .catch((error) => {
        if (live) setState((current) => ({ ...current, error }));
      });
    return () => {
      live = false;
    };
  }, [agent, owner.id, requested, revision]);
  return state;
}
