import { useEffect, useState } from "react";
import { api, isRequestCancelled, type Thread } from "../lib/api";
import { conversationKey, readConversation, retainConversation } from "../lib/conversation-cache";
import { useClient } from "../providers/ClientProvider";

const pending = new Map<string, Promise<Thread[]>>();
window.addEventListener("lonora:session-reset", () => pending.clear());
function load(owner: string, agent: string) {
  const key = conversationKey(owner, `/threads?agent_id=${agent}`);
  let promise = pending.get(key);
  if (!promise) {
    promise = api
      .get<Thread[]>(`/threads?agent_id=${agent}`)
      .then(async (rows) => {
        const direct = rows.filter((row) => !row.group_id);
        if (direct.length) return retainConversation(key, direct);
        return retainConversation(key, [
          await api.post<Thread>(`/agents/${agent}/conversation`, {}),
        ]);
      })
      .finally(() => {
        if (pending.get(key) === promise) pending.delete(key);
      });
    pending.set(key, promise);
  }
  return promise;
}
export function usePersistentThread(agent: string, requested?: string | null) {
  const { owner, revision } = useClient();
  const cacheKey = conversationKey(owner.id, `/threads?agent_id=${agent}`);
  const restored = readConversation<Thread[]>(cacheKey) ?? [];
  const initial =
    restored.find((row) => row.id === requested) ?? (!requested ? restored[0] : undefined);
  const [state, setState] = useState<{ thread?: Thread; threads: Thread[]; error?: unknown }>({
    threads: restored,
    thread: initial,
  });
  useEffect(() => {
    void agent;
    void owner.id;
    void requested;
    const rows = readConversation<Thread[]>(cacheKey) ?? [];
    setState((old) => ({
      threads: rows,
      thread:
        rows.find((row) => row.id === requested) ??
        (!requested ? old.thread && rows.find((row) => row.id === old.thread?.id) : undefined) ??
        (!requested ? rows[0] : undefined),
    }));
  }, [agent, owner.id, requested, cacheKey]);
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
        if (live && !isRequestCancelled(error)) setState((current) => ({ ...current, error }));
      });
    return () => {
      live = false;
    };
  }, [agent, owner.id, requested, revision]);
  if (
    state.thread &&
    (state.thread.agent_id !== agent || (requested && state.thread.id !== requested))
  )
    return { threads: restored, thread: initial };
  return state;
}
