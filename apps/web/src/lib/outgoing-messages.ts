import type { Message } from "./api";

export type OutgoingMessage = Message & {
  delivery: "sending" | "failed";
  retry_nonce: string;
};
export type OutgoingIntent = {
  fingerprint: string;
  nonce: string;
  message: OutgoingMessage;
  body: Record<string, unknown>;
};

const entries = new Map<string, OutgoingIntent[]>();
const uncertain = new Map<string, Map<string, OutgoingIntent>>();
const listeners = new Set<() => void>();
const empty: OutgoingIntent[] = [];
let sequence = 0;

export function outgoingKey(ownerId: string, threadId: string) {
  return JSON.stringify([ownerId, threadId]);
}
export function subscribeOutgoing(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function outgoingMessages(key: string): OutgoingIntent[] {
  return entries.get(key) ?? empty;
}
function save(key: string, rows: OutgoingIntent[]) {
  if (rows.length) entries.set(key, rows);
  else entries.delete(key);
  for (const listener of listeners) listener();
}
export function enqueueOutgoing(
  key: string,
  threadId: string,
  fingerprint: string,
  body: Record<string, unknown>,
): OutgoingIntent {
  const prior =
    outgoingMessages(key).find((row) => row.fingerprint === fingerprint) ??
    uncertain.get(key)?.get(fingerprint);
  if (prior) {
    const next = { ...prior, message: { ...prior.message, delivery: "sending" as const } };
    save(key, [...outgoingMessages(key).filter((row) => row.nonce !== prior.nonce), next]);
    return prior;
  }
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
      seq: Number.MAX_SAFE_INTEGER - 1_000_000 + ++sequence,
      role: "user",
      content: String(body.content ?? ""),
      reply_to: typeof body.reply_to === "string" ? body.reply_to : null,
      attachment_ids: Array.isArray(body.attachment_ids) ? [...body.attachment_ids] : [],
      created_at: new Date().toISOString(),
    },
  };
  save(key, [...outgoingMessages(key), intent]);
  return intent;
}
export function failOutgoing(key: string, nonce: string) {
  const intent = outgoingMessages(key).find((row) => row.nonce === nonce);
  if (intent) {
    const receipts = uncertain.get(key) ?? new Map<string, OutgoingIntent>();
    receipts.set(intent.fingerprint, intent);
    uncertain.set(key, receipts);
  }
  save(
    key,
    outgoingMessages(key).map((row) =>
      row.nonce === nonce ? { ...row, message: { ...row.message, delivery: "failed" } } : row,
    ),
  );
}
export function acknowledgeOutgoing(key: string, messages: Message[], httpConfirmed = false) {
  const nonces = new Set(messages.map((message) => message.client_nonce).filter(Boolean));
  if (httpConfirmed) {
    const receipts = uncertain.get(key);
    if (receipts)
      for (const [fingerprint, intent] of receipts)
        if (nonces.has(intent.nonce)) receipts.delete(fingerprint);
  }
  const current = outgoingMessages(key);
  const next = current.filter((row) => !nonces.has(row.nonce));
  if (next.length !== current.length) save(key, next);
}
export function isOutgoingMessage(message: Message): message is OutgoingMessage {
  return message.id.startsWith("pending:") && "delivery" in message && "retry_nonce" in message;
}

// Keep unacknowledged messages during navigation/reconnect, never across sessions.
if (typeof window !== "undefined")
  window.addEventListener("lonora:session-reset", () => {
    entries.clear();
    uncertain.clear();
    for (const listener of listeners) listener();
  });
