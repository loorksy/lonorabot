import { pendingVoiceRich } from "@lonora/core";
import { ApiError, type Message } from "./api";

export type OutgoingMessage = Message & {
  /** queued: offline, never answered by the server; flushes by itself (owner decision Q6). */
  delivery: "sending" | "queued" | "failed";
  retry_nonce: string;
};
/**
 * Whether the API itself answered a send (owner decision Q6). A proxy's 502 or 504 with no
 * Lonora error code means the API never saw it: a plain message waits for the next flush
 * under its own client_nonce, which the server deduplicates. Every 4xx and every 503 (the
 * app's own maintenance and database errors) is an answer.
 */
export function serverAnswered(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    !((error.status === 502 || error.status === 504) && error.code === "request_failed")
  );
}
export type OutgoingIntent = {
  fingerprint: string;
  nonce: string;
  message: OutgoingMessage;
  body: Record<string, unknown>;
};

const entries = new Map<string, OutgoingIntent[]>();
const loaded = new Set<string>();
const prefix = "lonora:outbox:v1:";
const listeners = new Set<() => void>();
const empty: OutgoingIntent[] = [];
let version = 0;
/** Changes whenever any outbox changes (the chat list's waiting and failed marks). */
export const outgoingVersion = () => version;

export function outgoingKey(ownerId: string, threadId: string) {
  return JSON.stringify([ownerId, threadId]);
}
export function subscribeOutgoing(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function outgoingMessages(key: string): OutgoingIntent[] {
  if (!loaded.has(key)) {
    loaded.add(key);
    try {
      const saved = JSON.parse(localStorage.getItem(prefix + key) ?? "null") as
        | OutgoingIntent[]
        | null;
      if (
        Array.isArray(saved) &&
        saved.length <= 100 &&
        saved.every(
          (row) =>
            typeof row.nonce === "string" &&
            typeof row.fingerprint === "string" &&
            row.body?.client_nonce === row.nonce &&
            row.message?.id === `pending:${row.nonce}` &&
            row.message.role === "user" &&
            row.message.thread_id === JSON.parse(key)[1] &&
            typeof row.message.content === "string" &&
            Array.isArray(row.message.attachment_ids),
        )
      ) {
        entries.set(
          key,
          // Only a message the server never answered keeps waiting; anything that was in
          // flight when the page went away needs the owner's retry.
          saved.map((row) => ({
            ...row,
            message: {
              ...row.message,
              delivery: row.message.delivery === "queued" ? "queued" : "failed",
            },
          })),
        );
      }
    } catch {
      /* Closed storage or corrupt local state cannot replace server history. */
    }
  }
  return entries.get(key) ?? empty;
}
/** Every message of this owner still waiting to go out, over all threads (the network strip). */
export function queuedOutgoingCount(ownerId: string) {
  let count = 0;
  for (const key of ownerKeys(ownerId))
    count += outgoingMessages(key).filter((row) => row.message.delivery !== "failed").length;
  return count;
}
function save(key: string, rows: OutgoingIntent[]) {
  version += 1;
  if (rows.length) entries.set(key, rows);
  else entries.delete(key);
  try {
    if (rows.length) localStorage.setItem(prefix + key, JSON.stringify(rows));
    else localStorage.removeItem(prefix + key);
  } catch {
    /* Memory still retains the recoverable outgoing message. */
  }
  for (const listener of listeners) listener();
}
export function enqueueOutgoing(
  key: string,
  threadId: string,
  fingerprint: string,
  body: Record<string, unknown>,
  afterSeq = 0,
): OutgoingIntent {
  const prior = outgoingMessages(key).find((row) => row.fingerprint === fingerprint);
  if (prior) {
    const next = { ...prior, message: { ...prior.message, delivery: "sending" as const } };
    save(
      key,
      outgoingMessages(key).map((row) => (row.nonce === prior.nonce ? next : row)),
    );
    return next;
  }
  if (outgoingMessages(key).length >= 100) throw new Error("outbox_full");
  const nonce = crypto.randomUUID();
  const intent: OutgoingIntent = {
    fingerprint,
    nonce,
    body: { ...body, client_nonce: nonce },
    message: {
      id: `pending:${nonce}`,
      client_nonce: nonce,
      retry_nonce: nonce,
      delivery: "sending",
      thread_id: threadId,
      agent_id: null,
      // Local sequence is presentation only. The server's accepted seq always wins.
      seq: Math.max(afterSeq, ...outgoingMessages(key).map((row) => row.message.seq)) + 0.25,
      role: "user",
      content: String(body.content ?? ""),
      // A voice note is drawn as one while it is sending or failed, never as a blank bubble.
      rich_content: pendingVoiceRich(body),
      reply_to: typeof body.reply_to === "string" ? body.reply_to : null,
      attachment_ids: Array.isArray(body.attachment_ids) ? [...body.attachment_ids] : [],
      created_at: new Date().toISOString(),
    },
  };
  save(key, [...outgoingMessages(key), intent]);
  return intent;
}
export function failOutgoing(
  key: string,
  nonce: string,
  delivery: OutgoingMessage["delivery"] = "failed",
) {
  save(
    key,
    outgoingMessages(key).map((row) =>
      row.nonce === nonce ? { ...row, message: { ...row.message, delivery } } : row,
    ),
  );
}
/** «حذف» on a failed message: it leaves the outbox (it never reached the server). */
export function dropOutgoing(key: string, nonce: string) {
  save(
    key,
    outgoingMessages(key).filter((row) => row.nonce !== nonce),
  );
}
/** The owner's keys with an outbox, in memory or saved on this device. */
function ownerKeys(ownerId: string): string[] {
  const keys = new Set(entries.keys());
  try {
    for (let index = 0; index < localStorage.length; index++) {
      const name = localStorage.key(index);
      if (name?.startsWith(prefix)) keys.add(name.slice(prefix.length));
    }
  } catch {
    /* Closed storage: the in-memory queue still counts. */
  }
  return [...keys].filter((key) => {
    try {
      return JSON.parse(key)[0] === ownerId;
    } catch {
      return false;
    }
  });
}
let flushing = false;
/**
 * Owner decision Q6: when the network returns, the messages that waited go out by
 * themselves under their own client_nonce (the server deduplicates). Only queued plain
 * messages are here; a refused one becomes «failed» with a manual retry.
 */
export async function flushQueued(
  ownerId: string,
  post: (threadId: string, body: Record<string, unknown>) => Promise<Message>,
  answered: (error: unknown) => boolean,
): Promise<number> {
  if (flushing) return 0;
  flushing = true;
  let sent = 0;
  try {
    for (const key of ownerKeys(ownerId)) {
      const threadId = JSON.parse(key)[1] as string;
      for (const row of outgoingMessages(key).filter(
        (item) => item.message.delivery === "queued",
      )) {
        failOutgoing(key, row.nonce, "sending");
        try {
          const message = await post(threadId, row.body);
          acknowledgeOutgoing(key, [message], true);
          sent += 1;
        } catch (error) {
          failOutgoing(key, row.nonce, answered(error) ? "failed" : "queued");
          if (!answered(error)) return sent;
        }
      }
    }
    return sent;
  } finally {
    flushing = false;
  }
}
export function acknowledgeOutgoing(key: string, messages: Message[], httpConfirmed = false) {
  const nonces = new Set(messages.map((message) => message.client_nonce).filter(Boolean));
  void httpConfirmed; // A canonical nonce acknowledges the same committed receipt over HTTP or SSE.
  const current = outgoingMessages(key);
  const next = current.filter((row) => !nonces.has(row.nonce));
  if (next.length !== current.length) save(key, next);
}
export function isOutgoingMessage(message: Message): message is OutgoingMessage {
  return message.id.startsWith("pending:") && "delivery" in message && "retry_nonce" in message;
}

// Recover pending text after reload without automatically resubmitting uncertain work.
// Session reset removes persisted private drafts/outbox for the departing principal.
if (typeof window !== "undefined")
  window.addEventListener("lonora:session-reset", () => {
    entries.clear();
    loaded.clear();
    try {
      for (const key of Object.keys(localStorage))
        if (key.startsWith(prefix)) localStorage.removeItem(key);
    } catch {
      /* Storage may be denied. */
    }
    for (const listener of listeners) listener();
  });
