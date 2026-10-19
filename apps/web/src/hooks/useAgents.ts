import { useEffect, useState } from "react";
import { type Agent, api, isRequestCancelled } from "../lib/api";
import { conversationKey, readConversation, retainConversation } from "../lib/conversation-cache";
import { useClient } from "../providers/ClientProvider";
export function useAgents() {
  const { owner, revision, refresh } = useClient();
  const key = conversationKey(owner.id, "/agents");
  const [agents, setAgents] = useState<Agent[]>(() => readConversation<Agent[]>(key) ?? []);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(() => readConversation(key) === undefined);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    let live = true;
    api
      .get<Agent[]>("/agents")
      .then((v) => {
        if (live) {
          setAgents(retainConversation(key, v));
          setError(undefined);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (live && !isRequestCancelled(e)) {
          setError(e);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [revision, key]);
  return {
    agents,
    error,
    loading,
    create: async (
      name: string,
      avatar: string,
      color: string,
      profile?: {
        title?: string;
        description?: string;
        trading_account_id: string;
        trading_symbol: string;
      },
    ) => {
      const agent = await api.post<Agent>("/agents", { name, avatar, color, ...profile });
      setAgents((rows) =>
        retainConversation(key, rows.some((row) => row.id === agent.id) ? rows : [...rows, agent]),
      );
      refresh();
      return agent;
    },
    update: async (id: string, body: Partial<Agent>) => {
      await api.patch(`/agents/${id}`, body);
      refresh();
    },
    remove: async (id: string) => {
      await api.delete(`/agents/${encodeURIComponent(id)}`);
      setAgents((rows) =>
        retainConversation(
          key,
          rows.filter((row) => row.id !== id),
        ),
      );
      refresh();
    },
  };
}
