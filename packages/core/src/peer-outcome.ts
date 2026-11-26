import type { Resource } from "@lonora/contracts";

const wrapper = /^<peer_outcome\b[^>]*status=['"]([^'"]+)['"][^>]*>\n([\s\S]*)\n<\/peer_outcome>$/;

/**
 * A colleague's result reaches the conversation inside a machine wrapper (run id and
 * status) that agents read; the owner sees only the result. A text without the wrapper
 * comes back unchanged.
 */
export function peerOutcome(content: string): { body: string; status?: string } {
  const match = wrapper.exec(content);
  return match ? { body: match[2], status: match[1] } : { body: content };
}

/** The message ids a peer exchange (agent ↔ agent) is shown on, in both conversations. */
export function peersByMessage(peers: Resource[]): Map<string, Resource> {
  const out = new Map<string, Resource>();
  for (const peer of peers) {
    const payload = peer.payload;
    for (const id of [
      payload.source_message_id,
      payload.target_message_id,
      payload.source_outcome_message_id,
      payload.target_outcome_message_id,
      ...(Array.isArray(payload.source_outcome_message_ids)
        ? payload.source_outcome_message_ids
        : []),
    ])
      if (typeof id === "string") out.set(id, peer);
  }
  return out;
}

/** One side of an exchange: the agent, its name and its conversation ("" when not stored). */
export type PeerParty = { id: string; name: string; thread: string };

/** The status line under a peer card; each client words it in its own catalog. */
export type PeerStatus = "cancelled" | "failed" | "completed" | "limited" | "working" | "queued";

export type PeerCard = {
  /** The request between the agents, or the result that came back. */
  kind: "request" | "outcome";
  /** Who wrote this message: the asker of a request, the answerer of a result. */
  from: PeerParty;
  to: PeerParty;
  status: PeerStatus;
  /** The request or the result without its wrapper; null for a bare cancellation. */
  body: string | null;
};

/**
 * What a persisted peer exchange shows on one of its messages, the same on Web and Mobile:
 * who asked whom, the status (the result's own, then the live run's, then the stored row's)
 * and the text.
 */
export function peerCard(
  message: { id: string; content: string },
  peer: Resource,
  runStatus?: string | null,
): PeerCard {
  const payload = peer.payload;
  const request =
    payload.source_message_id === message.id || payload.target_message_id === message.id;
  const wrapped = peerOutcome(message.content);
  const side = (a: unknown, b: unknown) => String((request ? a : b) ?? "");
  const from = {
    id: side(payload.source_agent_id, payload.target_agent_id),
    name: side(payload.source_agent_name, payload.target_agent_name),
    thread: side(payload.source_thread_id, payload.target_thread_id),
  };
  const to = {
    id: side(payload.target_agent_id, payload.source_agent_id),
    name: side(payload.target_agent_name, payload.source_agent_name),
    thread: side(payload.target_thread_id, payload.source_thread_id),
  };
  const raw = wrapped.status ?? runStatus ?? String(payload.status ?? "queued");
  const status: PeerStatus = ["cancelled", "failed", "completed", "limited"].includes(raw)
    ? (raw as PeerStatus)
    : ["running", "leased"].includes(raw)
      ? "working"
      : "queued";
  return {
    kind: request ? "request" : "outcome",
    from,
    to,
    status,
    body: raw === "cancelled" && wrapped.body === "cancelled" ? null : wrapped.body,
  };
}
