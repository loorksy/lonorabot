import type { MentionAddress } from "@lonora/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, isRequestCancelled, type Message, type Run, type Thread } from "../lib/api";
import { conversationKey, readConversation, retainConversation } from "../lib/conversation-cache";
import { useClient } from "../providers/ClientProvider";
export function useThreads(agentId?: string, threadId?: string) {
  const { owner, revision, refresh, events } = useClient();
  const [threads, setThreads] = useState<Thread[]>([]);
  const messageKey = conversationKey(owner.id, `/threads/${threadId}/messages`);
  const runKey = conversationKey(owner.id, `/runs?thread_id=${threadId}`);
  const [messages, setMessages] = useState<Message[]>(
    () => readConversation<Message[]>(messageKey) ?? [],
  );
  const [runs, setRuns] = useState<Run[]>(() => readConversation<Run[]>(runKey) ?? []);
  const [error, setError] = useState<unknown>();
  const [listingError, setListingError] = useState<unknown>();
  const pendingSend = useRef<{ fingerprint: string; nonce: string } | null>(null);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    if (!agentId && threadId) return;
    let live = true;
    api
      .get<Thread[]>(`/threads${agentId ? `?agent_id=${agentId}` : ""}`)
      .then((v) => {
        if (live) {
          setThreads(v);
          setListingError(undefined);
        }
      })
      .catch((e) => {
        if (live && !isRequestCancelled(e)) setListingError(e);
      });
    return () => {
      live = false;
    };
  }, [agentId, threadId, revision]);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void threadId;
    pendingSend.current = null;
    setMessages(readConversation<Message[]>(messageKey) ?? []);
    setRuns(readConversation<Run[]>(runKey) ?? []);
    setError(undefined);
  }, [threadId, messageKey, runKey]);
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
            const result = [...merged.values()].sort((a, b) => a.seq - b.seq);
            retainConversation(messageKey, result.slice(-500));
            return result;
          });
          setRuns(retainConversation(runKey, r));
          setError(undefined);
        }
      })
      .catch((e) => {
        if (live && !isRequestCancelled(e)) setError(e);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision, messageKey, runKey]);
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
    error: error ?? listingError,
    create: async (id: string) => {
      const thread = await api.post<Thread>("/threads", { agent_id: id, title: "" });
      refresh();
      return thread;
    },
    send: async (
      content: string,
      attachment_ids: string[] = [],
      reply_to: string | null = null,
      mentions?: MentionAddress,
    ) => {
      // A response can be lost after the server has committed this intent and its run.
      // Retry unchanged content with the same receipt key; a confirmed repeat gets a new key.
      const fingerprint = JSON.stringify([threadId, content, attachment_ids, reply_to, mentions]);
      if (pendingSend.current?.fingerprint !== fingerprint)
        pendingSend.current = { fingerprint, nonce: crypto.randomUUID() };
      const nonce = pendingSend.current.nonce;
      await api.post(`/threads/${threadId}/messages`, {
        content,
        attachment_ids,
        reply_to,
        client_nonce: nonce,
        mention_agent_ids: mentions?.agent_ids ?? [],
        mention_all: mentions?.all ?? false,
        collaboration_session_id: mentions?.collaboration_session_id,
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
