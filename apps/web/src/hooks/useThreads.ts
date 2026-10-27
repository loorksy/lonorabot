import type { InputAnswer } from "@lonora/contracts";
import { type MentionAddress, projectRunEvents } from "@lonora/core";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { api, isRequestCancelled, type Message, type Run, type Thread } from "../lib/api";
import { conversationKey, readConversation, retainConversation } from "../lib/conversation-cache";
import {
  acknowledgeOutgoing,
  enqueueOutgoing,
  failOutgoing,
  type OutgoingIntent,
  outgoingKey,
  outgoingMessages,
  subscribeOutgoing,
} from "../lib/outgoing-messages";
import { useClient } from "../providers/ClientProvider";

const inFlightSends = new Map<string, Promise<void>>();

function mergeMessages(...groups: Message[][]) {
  const messages = new Map(groups.flat().map((message) => [message.id, message]));
  return [...messages.values()].sort((a, b) => a.seq - b.seq);
}

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
  const [runError, setRunError] = useState<unknown>();
  const [listingError, setListingError] = useState<unknown>();
  const key = outgoingKey(owner.id, threadId ?? "");
  const outgoing = useSyncExternalStore(subscribeOutgoing, () => outgoingMessages(key));
  const selectedKey = useRef(messageKey);
  selectedKey.current = messageKey;
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
    setMessages(readConversation<Message[]>(messageKey) ?? []);
    setRuns(readConversation<Run[]>(runKey) ?? []);
    setError(undefined);
    setRunError(undefined);
  }, [threadId, messageKey, runKey]);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    if (!threadId) return;
    let live = true;
    // Message visibility must never wait for the independent Run projection.
    api
      .get<Message[]>(`/threads/${threadId}/messages`)
      .then((m) => {
        if (live) {
          setMessages((old) => {
            const result = mergeMessages(old, m);
            retainConversation(messageKey, result.slice(-500));
            return result;
          });
          setError(undefined);
        }
      })
      .catch((e) => {
        if (live && !isRequestCancelled(e)) setError(e);
      });
    api
      .get<Run[]>(`/runs?thread_id=${threadId}`)
      .then((r) => {
        if (live) {
          setRuns((old) =>
            retainConversation(runKey, projectRunEvents([...old, ...r], [], threadId)),
          );
          setRunError(undefined);
        }
      })
      .catch((e) => {
        if (live && !isRequestCancelled(e)) setRunError(e);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision, messageKey, runKey]);
  const canonicalMessages = useMemo(() => {
    // An accepted send may finish while this viewport is unmounted. Its scoped
    // cache and outbox notification restore it on navigation without another GET.
    void outgoing;
    const visible = new Map(
      mergeMessages(readConversation<Message[]>(messageKey) ?? [], messages)
        .filter((message) => message.thread_id === threadId)
        .map((message) => [message.id, message]),
    );
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
  }, [messages, events, threadId, messageKey, outgoing]);
  useEffect(() => {
    retainConversation(messageKey, canonicalMessages.slice(-500));
    acknowledgeOutgoing(key, canonicalMessages);
  }, [canonicalMessages, messageKey, key]);
  const projectedRuns = useMemo(
    () => projectRunEvents(runs, events, threadId),
    [runs, events, threadId],
  );
  useEffect(() => {
    retainConversation(runKey, projectedRuns);
  }, [runKey, projectedRuns]);
  const visibleMessages = useMemo(() => {
    const accepted = new Set(canonicalMessages.map((message) => message.client_nonce));
    const pending = outgoing.filter((row) => !accepted.has(row.nonce));
    const after = Math.max(0, ...canonicalMessages.map((message) => message.seq));
    return mergeMessages(
      canonicalMessages,
      pending.map((row, index) => ({
        ...row.message,
        // Canonical integer sequences win as earlier concurrent sends arrive.
        // Remaining optimistic rows keep their order after the accepted history.
        seq: after + (index + 1) / (pending.length + 1),
      })),
    );
  }, [canonicalMessages, outgoing]);

  async function deliver(intent: OutgoingIntent): Promise<void> {
    if (!threadId) throw new Error("thread_not_found");
    const flightKey = `${key}:${intent.nonce}`;
    const existing = inFlightSends.get(flightKey);
    if (existing) return existing;
    const operation = (async () => {
      try {
        const accepted = await api.post<{ message: Message; run_ids: string[]; runs?: Run[] }>(
          `/threads/${threadId}/messages`,
          intent.body,
        );
        const saved = mergeMessages(readConversation<Message[]>(messageKey) ?? [], [
          accepted.message,
        ]);
        retainConversation(messageKey, saved.slice(-500));
        if (selectedKey.current === messageKey) setMessages(saved);
        const acknowledgedRuns = projectRunEvents(
          [...(readConversation<Run[]>(runKey) ?? []), ...(accepted.runs ?? [])],
          [],
          threadId,
        );
        retainConversation(runKey, acknowledgedRuns);
        if (selectedKey.current === messageKey) setRuns(acknowledgedRuns);
        acknowledgeOutgoing(key, [accepted.message], true);
        refresh();
      } catch (caught) {
        // A live event can independently confirm a committed send whose HTTP
        // response was lost. It must not turn into a misleading failed bubble.
        const confirmed = readConversation<Message[]>(messageKey)?.find(
          (message) => message.client_nonce === intent.nonce,
        );
        if (confirmed) {
          acknowledgeOutgoing(key, [confirmed], true);
          refresh();
          return;
        }
        if (!isRequestCancelled(caught)) failOutgoing(key, intent.nonce);
        throw caught;
      }
    })().finally(() => inFlightSends.delete(flightKey));
    inFlightSends.set(flightKey, operation);
    return operation;
  }
  function queueIntent(
    content: string,
    attachment_ids: string[] = [],
    reply_to: string | null = null,
    mentions?: MentionAddress,
    inputAnswer?: InputAnswer,
  ): OutgoingIntent {
    if (!threadId) throw new Error("thread_not_found");
    const fingerprint = JSON.stringify([
      threadId,
      content,
      attachment_ids,
      reply_to,
      mentions,
      inputAnswer,
    ]);
    const intent = enqueueOutgoing(
      key,
      threadId,
      fingerprint,
      {
        content,
        attachment_ids,
        reply_to,
        ...(inputAnswer ? { input_answer: inputAnswer } : {}),
        mention_agent_ids: mentions?.agent_ids ?? [],
        mention_all: mentions?.all ?? false,
        collaboration_session_id: mentions?.collaboration_session_id,
      },
      Math.max(0, ...canonicalMessages.map((message) => message.seq)),
    );
    return intent;
  }
  return {
    threads,
    messages: visibleMessages,
    runs: projectedRuns,
    error: error ?? runError ?? listingError,
    create: async (id: string) => {
      const thread = await api.post<Thread>("/threads", { agent_id: id, title: "" });
      refresh();
      return thread;
    },
    // Synchronous acceptance is the composer's draft boundary. Network failures
    // remain on the existing outgoing bubble, with the same nonce for Retry.
    queue: (...args: Parameters<typeof queueIntent>) => {
      const intent = queueIntent(...args);
      void deliver(intent).catch(() => undefined);
    },
    send: async (...args: Parameters<typeof queueIntent>) => {
      await deliver(queueIntent(...args));
    },
    retry: async (nonce: string) => {
      if (!threadId) return;
      const prior = outgoingMessages(key).find((row) => row.nonce === nonce);
      if (!prior) return;
      await deliver(enqueueOutgoing(key, threadId, prior.fingerprint, prior.body));
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
