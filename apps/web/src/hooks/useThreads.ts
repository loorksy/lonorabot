import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Message, type Run, type Thread } from "../lib/api";
import { useClient } from "../providers/ClientProvider";
export function useThreads(agentId?: string, threadId?: string) {
  const { revision, refresh, events } = useClient();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<unknown>();
  const pendingSend = useRef<{ fingerprint: string; nonce: string } | null>(null);
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
    pendingSend.current = null;
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
          setMessages((old) => {
            const merged = new Map(old.map((message) => [message.id, message]));
            for (const message of m) merged.set(message.id, message);
            return [...merged.values()].sort((a, b) => a.seq - b.seq);
          });
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
  const visibleMessages = useMemo(() => {
    const visible = new Map(messages.map((message) => [message.id, message]));
    for (const event of events) {
      if (
        !["message.created", "message.updated"].includes(event.kind) ||
        event.thread_id !== threadId
      )
        continue;
      const payload = event.payload;
      if (
        typeof payload.id !== "string" ||
        typeof payload.content !== "string" ||
        typeof payload.seq !== "number" ||
        typeof payload.created_at !== "string" ||
        !Array.isArray(payload.attachment_ids) ||
        !["user", "assistant", "system", "tool"].includes(String(payload.role))
      )
        continue;
      visible.set(payload.id, payload as unknown as Message);
    }
    return [...visible.values()].sort((a, b) => a.seq - b.seq);
  }, [messages, events, threadId]);
  return {
    threads,
    messages: visibleMessages,
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
      // A response can be lost after the server has committed this intent and its run.
      // Retry unchanged content with the same receipt key; a confirmed repeat gets a new key.
      const fingerprint = JSON.stringify([threadId, content, attachment_ids, reply_to]);
      if (pendingSend.current?.fingerprint !== fingerprint)
        pendingSend.current = { fingerprint, nonce: crypto.randomUUID() };
      const nonce = pendingSend.current.nonce;
      await api.post(`/threads/${threadId}/messages`, {
        content,
        attachment_ids,
        reply_to,
        client_nonce: nonce,
      });
      if (pendingSend.current?.nonce === nonce) pendingSend.current = null;
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
      setMessages((old) => {
        const merged = new Map(old.map((message) => [message.id, message]));
        for (const message of rows) merged.set(message.id, message);
        return [...merged.values()].sort((a, b) => a.seq - b.seq);
      });
    },
    remove: async (id: string) => {
      await api.delete(`/threads/${id}`);
      refresh();
    },
  };
}
