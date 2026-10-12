import { useEffect, useState } from "react";
import { api, type Message, type Run, type Thread } from "../lib/api";
import { useClient } from "../providers/ClientProvider";
export function useThreads(agentId?: string, threadId?: string) {
  const { revision, refresh } = useClient();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    let live = true;
    api
      .get<Thread[]>(`/threads${agentId ? `?agent_id=${agentId}` : ""}`)
      .then((v) => {
        if (live) setThreads(v);
      })
      .catch((e) => {
        if (live) setError(e);
      });
    return () => {
      live = false;
    };
  }, [agentId, revision]);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void threadId;
    setMessages([]);
    setRuns([]);
  }, [threadId]);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    if (!threadId) return;
    let live = true;
    Promise.all([
      api.get<Message[]>(`/threads/${threadId}/messages`),
      api.get<Run[]>(`/runs?thread_id=${threadId}`),
    ])
      .then(([m, r]) => {
        if (live) {
          setMessages(m);
          setRuns(r);
          setError(undefined);
        }
      })
      .catch((e) => {
        if (live) setError(e);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision]);
  return {
    threads,
    messages,
    runs,
    error,
    create: async (id: string) => {
      const thread = await api.post<Thread>("/threads", { agent_id: id, title: "" });
      refresh();
      return thread;
    },
    send: async (
      content: string,
      attachment_ids: string[] = [],
      reply_to: string | null = null,
    ) => {
      await api.post(`/threads/${threadId}/messages`, {
        content,
        attachment_ids,
        reply_to,
        client_nonce: crypto.randomUUID(),
      });
      refresh();
    },
    cancel: async (id: string) => {
      await api.post(`/runs/${id}/cancel`, {});
      refresh();
    },
    resume: async (id: string) => {
      await api.post(`/runs/${id}/resume`, {});
      refresh();
    },
    older: async () => {
      if (!threadId || !messages.length) return;
      const rows = await api.get<Message[]>(
        `/threads/${threadId}/messages?before=${messages[0].seq}`,
      );
      setMessages((old) => [...rows, ...old]);
    },
    remove: async (id: string) => {
      await api.delete(`/threads/${id}`);
      refresh();
    },
  };
}
