/** Recoverable owner-scoped send intents, never an alternate conversation store. */
import type { Message } from "@lonora/contracts";
import { Platform } from "react-native";
import { registerSessionTeardown } from "./session-lifecycle";

export type OutgoingMessage = Message & { delivery: "sending" | "failed"; retry_nonce: string };
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
        restored.push({
          ...item,
          body: { ...item.body, client_nonce: item.nonce },
          message: { ...item.message, delivery: "failed" },
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
export function failOutgoing(key: string, nonce: string) {
  notify(
    key,
    outgoingMessages(key).map((row) =>
      row.nonce === nonce
        ? { ...row, message: { ...row.message, delivery: "failed" as const } }
        : row,
    ),
  );
  void persist(key).catch(() => undefined);
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
