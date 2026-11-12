/** Recoverable owner-scoped send intents, never an alternate conversation store. */
import type { Message } from "@lonora/contracts";
import { isPlainOutgoing, pendingVoiceRich } from "@lonora/core";
import { Platform } from "react-native";
import { ApiError } from "./api-error";
import { registerSessionTeardown } from "./session-lifecycle";

export type OutgoingMessage = Message & {
  /** queued: the API never answered it; it goes out by itself when the network returns (Q6). */
  delivery: "sending" | "queued" | "failed";
  retry_nonce: string;
};
/**
 * Whether the API itself answered a send (Q6, as on Web). No response at all, or a proxy's
 * bare 502/504 with no Lonora error code, means the API never saw it. Every 4xx and every
 * 503 (the app's own maintenance and database errors) is an answer.
 */
export function serverAnswered(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    !((error.status === 502 || error.status === 504) && error.code === "request_failed")
  );
}
/**
 * A send that waits for the network instead of failing: plain owner text the API never
 * answered. An input answer, an edit, a card submit or a voice note never waits, and a
 * request the session itself cancelled (sign-out, server change) is not a network loss.
 */
export function waitsForNetwork(error: unknown, body: Readonly<Record<string, unknown>>) {
  if ((error as { name?: unknown } | null)?.name === "SessionRequestCancelled") return false;
  return !serverAnswered(error) && isPlainOutgoing(body);
}
export type OutgoingIntent = {
  nonce: string;
  fingerprint: string;
  body: Record<string, unknown>;
  message: OutgoingMessage;
};
const entries = new Map<string, OutgoingIntent[]>();
const listeners = new Set<() => void>();
const writes = new Map<string, Promise<void>>();
const hydration = new Map<string, Promise<void>>();
const empty: OutgoingIntent[] = [];
const PREFIX = "lonora.outbox.v1:";
const MAX_BYTES = 1024 * 1024;
let generation = 0;
export const outgoingKey = (server: string, owner: string, thread: string) =>
  JSON.stringify([server, owner, thread]);
export const outgoingMessages = (key: string): OutgoingIntent[] => entries.get(key) ?? empty;
/**
 * Every outbox of this server and owner known on this device: those the chat list hydrated
 * and those of any other conversation opened (a routine's, a task's or a chart's thread).
 */
export function ownerOutgoingKeys(server: string, owner: string): string[] {
  return [...entries.keys()].filter((key) => {
    const [keyServer, keyOwner] = JSON.parse(key) as string[];
    return keyServer === server && keyOwner === owner;
  });
}
export function subscribeOutgoing(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
function notify(key: string, rows: OutgoingIntent[]) {
  if (rows.length) entries.set(key, rows);
  else entries.delete(key);
  for (const listener of listeners) listener();
}
function filename(key: string) {
  let first = 2166136261,
    second = 2654435769;
  for (const char of key) {
    first = Math.imul(first ^ char.charCodeAt(0), 16777619);
    second = Math.imul(second ^ char.charCodeAt(0), 2246822507);
  }
  return `${(first >>> 0).toString(16)}-${(second >>> 0).toString(16)}.json`;
}
async function nativeFile(key: string) {
  const { Directory, File, Paths } = await import("expo-file-system");
  const directory = new Directory(Paths.document, "lonora-outbox");
  return { directory, file: new File(directory, filename(key)) };
}
function persist(key: string): Promise<void> {
  const epoch = generation;
  const next = (writes.get(key) ?? Promise.resolve())
    .catch(() => undefined)
    .then(async () => {
      if (epoch !== generation) return;
      const raw = JSON.stringify(outgoingMessages(key));
      if (raw.length > MAX_BYTES) throw new Error("outbox_full");
      if (Platform.OS === "web") {
        if (!globalThis.localStorage) throw new Error("outbox_unavailable");
        if (raw === "[]") globalThis.localStorage.removeItem(PREFIX + key);
        else globalThis.localStorage.setItem(PREFIX + key, raw);
      } else {
        const { directory, file } = await nativeFile(key);
        if (epoch !== generation) return;
        directory.create({ intermediates: true, idempotent: true });
        file.write(raw);
      }
    });
  writes.set(key, next);
  return next;
}
export function hydrateOutgoing(key: string): Promise<void> {
  const current = hydration.get(key);
  if (current) return current;
  const epoch = generation;
  const operation = (async () => {
    let raw: string | null;
    try {
      if (Platform.OS === "web") raw = globalThis.localStorage?.getItem(PREFIX + key) ?? null;
      else {
        const { file } = await nativeFile(key);
        raw = file.exists ? await file.text() : null;
      }
      if (!raw || raw.length > MAX_BYTES || epoch !== generation) return;
      const value: unknown = JSON.parse(raw);
      if (!Array.isArray(value) || value.length > 30) return;
      const restored: OutgoingIntent[] = [];
      for (const item of value) {
        if (
          !item ||
          typeof item !== "object" ||
          typeof item.nonce !== "string" ||
          item.nonce.length > 100 ||
          typeof item.fingerprint !== "string" ||
          !item.body ||
          typeof item.body.content !== "string" ||
          item.body.content.length > 30000 ||
          !item.message ||
          item.message.role !== "user" ||
          item.message.client_nonce !== item.nonce ||
          item.message.id !== `pending:${item.nonce}` ||
          !Array.isArray(item.message.attachment_ids)
        )
          continue;
        // Only a message the server never answered keeps waiting; one that was in flight
        // when the app went away needs the owner's retry.
        const queued = item.message.delivery === "queued" && isPlainOutgoing(item.body);
        restored.push({
          ...item,
          body: { ...item.body, client_nonce: item.nonce },
          message: { ...item.message, delivery: queued ? "queued" : "failed" },
        });
      }
      const existing = outgoingMessages(key);
      notify(key, [
        ...restored.filter((row) => !existing.some((item) => item.nonce === row.nonce)),
        ...existing,
      ]);
    } catch {
      /* A missing cache cannot replace the authenticated transcript. */
    }
  })();
  hydration.set(key, operation);
  return operation;
}
export async function enqueueOutgoing(
  key: string,
  thread: string,
  fingerprint: string,
  body: Record<string, unknown>,
  afterSeq: number,
): Promise<OutgoingIntent> {
  const epoch = generation;
  await hydrateOutgoing(key);
  if (epoch !== generation) throw new Error("session_request_cancelled");
  const prior = outgoingMessages(key).find((row) => row.fingerprint === fingerprint);
  if (prior) {
    const intent = { ...prior, message: { ...prior.message, delivery: "sending" as const } };
    notify(
      key,
      outgoingMessages(key).map((row) => (row.nonce === intent.nonce ? intent : row)),
    );
    try {
      await persist(key);
      if (epoch !== generation) throw new Error("session_request_cancelled");
    } catch (error) {
      if (epoch === generation) failOutgoing(key, intent.nonce);
      throw error;
    }
    return intent;
  }
  if (outgoingMessages(key).length >= 30) throw new Error("outbox_full");
  const nonce =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  const intent: OutgoingIntent = {
    nonce,
    fingerprint,
    body: { ...body, client_nonce: nonce },
    message: {
      id: `pending:${nonce}`,
      client_nonce: nonce,
      retry_nonce: nonce,
      delivery: "sending",
      thread_id: thread,
      agent_id: null,
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
  notify(key, [...outgoingMessages(key), intent]);
  try {
    await persist(key);
    if (epoch !== generation) throw new Error("session_request_cancelled");
  } catch (error) {
    notify(
      key,
      outgoingMessages(key).filter((row) => row.nonce !== nonce),
    );
    throw error;
  }
  return intent;
}
export function failOutgoing(
  key: string,
  nonce: string,
  delivery: OutgoingMessage["delivery"] = "failed",
) {
  notify(
    key,
    outgoingMessages(key).map((row) =>
      row.nonce === nonce ? { ...row, message: { ...row.message, delivery } } : row,
    ),
  );
  void persist(key).catch(() => undefined);
}
const flushedListeners = new Set<(key: string, message: Message) => void>();
/** The open conversation hears a message the flush delivered, as if it had sent it itself. */
export function subscribeFlushed(listener: (key: string, message: Message) => void) {
  flushedListeners.add(listener);
  return () => {
    flushedListeners.delete(listener);
  };
}
let flushing = false;
/**
 * Q6: when the network returns, the messages that waited go out by themselves, in order,
 * under their own client_nonce (the server deduplicates). The flush stops at the first send
 * the API still does not answer; a send it refuses becomes «failed» with a manual retry.
 * Returns how many were sent.
 */
export async function flushQueued(
  keys: readonly string[],
  post: (thread: string, body: Record<string, unknown>) => Promise<Message>,
): Promise<number> {
  if (flushing) return 0;
  flushing = true;
  const epoch = generation;
  let sent = 0;
  try {
    for (const key of keys) {
      const thread = JSON.parse(key)[2] as string;
      for (const row of outgoingMessages(key).filter(
        (item) => item.message.delivery === "queued",
      )) {
        if (epoch !== generation) return 0;
        failOutgoing(key, row.nonce, "sending");
        try {
          const message = await post(thread, row.body);
          // The session that queued it is gone: nothing is reported to the next one.
          if (epoch !== generation) return 0;
          acknowledgeOutgoing(key, [message]);
          for (const listener of flushedListeners) listener(key, message);
          sent += 1;
        } catch (error) {
          if (epoch !== generation) return 0;
          const waits = waitsForNetwork(error, row.body);
          failOutgoing(key, row.nonce, waits ? "queued" : "failed");
          if (waits) return sent;
        }
      }
    }
    return sent;
  } finally {
    flushing = false;
  }
}
export function acknowledgeOutgoing(key: string, messages: Message[]) {
  const nonces = new Set(messages.map((message) => message.client_nonce).filter(Boolean));
  const previous = outgoingMessages(key),
    next = previous.filter((row) => !nonces.has(row.nonce));
  if (next.length === previous.length) return;
  notify(key, next);
  void persist(key).catch(() => undefined);
}
export function isOutgoingMessage(message: Message): message is OutgoingMessage {
  return message.id.startsWith("pending:") && "delivery" in message && "retry_nonce" in message;
}
registerSessionTeardown(async () => {
  generation += 1;
  entries.clear();
  hydration.clear();
  for (const listener of listeners) listener();
  await Promise.allSettled([...writes.values()]);
  writes.clear();
  if (Platform.OS === "web") {
    for (const key of Object.keys(globalThis.localStorage ?? {}))
      if (key.startsWith(PREFIX)) globalThis.localStorage.removeItem(key);
  } else {
    const { Directory, Paths } = await import("expo-file-system");
    const directory = new Directory(Paths.document, "lonora-outbox");
    if (directory.exists) directory.delete();
  }
});
