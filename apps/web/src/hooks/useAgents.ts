import { useEffect, useState } from "react";
import { type Agent, api } from "../lib/api";
import { useClient } from "../providers/ClientProvider";
export function useAgents() {
  const { revision, refresh } = useClient();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    let live = true;
    api
      .get<Agent[]>("/agents")
      .then((v) => {
        if (live) {
          setAgents(v);
          setError(undefined);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (live) {
          setError(e);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [revision]);
  return {
    agents,
    error,
    loading,
    create: async (
      name: string,
      avatar: string,
      color: string,
      profile?: { title?: string; description?: string },
    ) => {
      const agent = await api.post<Agent>("/agents", { name, avatar, color, ...profile });
      setAgents((rows) => (rows.some((row) => row.id === agent.id) ? rows : [...rows, agent]));
      refresh();
      return agent;
    },
    update: async (id: string, body: Partial<Agent>) => {
      await api.patch(`/agents/${id}`, body);
      refresh();
    },
    remove: async (id: string) => {
      await api.delete(`/agents/${id}`);
      refresh();
    },
  };
}
