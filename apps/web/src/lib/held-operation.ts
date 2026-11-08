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
 * The journal statuses that settle an operation, as ``TERMINAL_STATUSES`` in
 * ``lonora_contracts.trading``: confirmed, failed (including never sent) or resolved
 * (by reconciliation or the owner's attestation). Reserved, submitted and ambiguous are
 * not settled, so the identity stays held and a retry asks the journal, never resends.
 */
const SETTLED: ReadonlySet<string> = new Set(["confirmed", "failed", "resolved"]);

/** Whether the outcome is settled, so the next click on this ticket is a new action. */
export function operationSettled(status: string): boolean {
  return SETTLED.has(status);
}

/**
 * Release the identity once the journal row is settled. The next click is then a new
 * operation: on a position or order that is still open (an uncertain close the owner
 * attested as not executed, a target changed by another action, a failed close) the
 * owner can act again, and on one that is gone it fails the executor's preflight against
 * fresh broker state, so nothing reaches the broker twice. Returns whether it released.
 */
export function settleOperation(
  action: string,
  accountId: string,
  ticket: string,
  status: string,
): boolean {
  if (!operationSettled(status)) return false;
  const name = key(action, accountId, ticket);
  const held = memory.delete(name);
  try {
    if (sessionStorage.getItem(name) == null) return held;
    sessionStorage.removeItem(name);
  } catch {
    return held;
  }
  return true;
}
