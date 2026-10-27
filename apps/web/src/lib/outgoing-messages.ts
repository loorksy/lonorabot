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
const loaded = new Set<string>();
const prefix = "lonora:outbox:v1:";
const listeners = new Set<() => void>();
const empty: OutgoingIntent[] = [];

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
          saved.map((row) => ({ ...row, message: { ...row.message, delivery: "failed" } })),
        );
      }
    } catch {
      /* Closed storage or corrupt local state cannot replace server history. */
    }
  }
  return entries.get(key) ?? empty;
}
function save(key: string, rows: OutgoingIntent[]) {
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
      reply_to: typeof body.reply_to === "string" ? body.reply_to : null,
      attachment_ids: Array.isArray(body.attachment_ids) ? [...body.attachment_ids] : [],
      created_at: new Date().toISOString(),
    },
  };
  save(key, [...outgoingMessages(key), intent]);
  return intent;
}
export function failOutgoing(key: string, nonce: string) {
  save(
    key,
    outgoingMessages(key).map((row) =>
      row.nonce === nonce ? { ...row, message: { ...row.message, delivery: "failed" } } : row,
    ),
  );
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
