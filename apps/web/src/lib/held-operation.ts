/**
 * One financial operation identity per owner action on a ticket, kept until its
 * outcome settles. A retry after a timeout, a double click or a reload sends the same
 * operation_id, which the executor answers from its journal instead of sending again.
 */

const PREFIX = "lonora.held-operation:";
// The page's own copy; sessionStorage adds survival across a reload of this tab.
const memory = new Map<string, string>();

function key(action: string, accountId: string, ticket: string): string {
  return `${PREFIX}${action}:${accountId}:${ticket}`;
}

/** The identity already held for this ticket action, if any. */
export function heldOperation(action: string, accountId: string, ticket: string): string | null {
  const name = key(action, accountId, ticket);
  try {
    return sessionStorage.getItem(name) ?? memory.get(name) ?? null;
  } catch {
    return memory.get(name) ?? null;
  }
}

/** The held identity, or a new one that is stored before anything is sent. */
export function holdOperation(action: string, accountId: string, ticket: string): string {
  const existing = heldOperation(action, accountId, ticket);
  if (existing) return existing;
  const operation = crypto.randomUUID();
  const name = key(action, accountId, ticket);
  memory.set(name, operation);
  try {
    sessionStorage.setItem(name, operation);
  } catch {
    // Without storage the identity still lives for this page.
  }
  return operation;
}

/**
 * Release the identity only when the journal shows the operation did not happen
 * (``failed``, including never sent): trying again is then a new operation. A confirmed
 * or resolved close keeps its identity for this ticket, so a row that is still on screen
 * answers from the journal instead of becoming a second close.
 */
export function settleOperation(
  action: string,
  accountId: string,
  ticket: string,
  status: string,
): void {
  if (status !== "failed") return;
  const name = key(action, accountId, ticket);
  memory.delete(name);
  try {
    sessionStorage.removeItem(name);
  } catch {
    // Nothing held.
  }
}
