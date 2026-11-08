import { useEffect, useRef, useState } from "react";
import type { Journal, Payload, Trade } from "../../lib/api";
import { heldOperation, holdOperation, settleOperation } from "../../lib/held-operation";
import { executeTrade } from "../../lib/trading";

export type TicketOutcome = { status: string; details?: unknown; code?: string | null };

/**
 * The owner's close/cancel button on one broker ticket. The operation_id is minted once
 * per ticket action and kept until its outcome settles (see ``settleOperation``), so a
 * double click, a retry after a timeout or a reload never creates a second operation.
 */
export function useTicketAction(
  action: "close_position" | "cancel_order",
  accountId: string,
  journal: Journal[] | undefined,
  onChange: () => void,
) {
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState("");
  const [results, setResults] = useState<Record<string, TicketOutcome>>({});
  // Synchronous guard: a second click before React re-renders sends nothing.
  const inflight = useRef(new Set<string>());
  useEffect(() => {
    // A held identity is released once the durable journal shows it did not happen.
    for (const entry of journal ?? []) {
      const ticket = String(
        entry.request[action === "close_position" ? "position_id" : "order_id"],
      );
      if (heldOperation(action, accountId, ticket) === entry.operation_id)
        settleOperation(action, accountId, ticket, entry.status);
    }
  }, [journal, action, accountId]);
  function outcome(ticket: string): TicketOutcome | null {
    const held = heldOperation(action, accountId, ticket);
    const entry = held ? journal?.find((row) => row.operation_id === held) : undefined;
    if (entry) return { status: entry.status, details: entry.result.details };
    return results[ticket] ?? null;
  }
  async function run(ticket: string, request: Omit<Trade, "operation_id" | "account_id">) {
    if (inflight.current.has(ticket)) return;
    inflight.current.add(ticket);
    setBusy(ticket);
    const operation = holdOperation(action, accountId, ticket);
    try {
      const result: Payload = await executeTrade({
        ...request,
        account_id: accountId,
        operation_id: operation,
      });
      const status = String(result.status);
      setResults((old) => ({
        ...old,
        [ticket]: { status, details: result.details, code: result.code as string | null },
      }));
      setError(undefined);
      settleOperation(action, accountId, ticket, status);
      onChange();
    } catch (caught) {
      // The identity stays held: retrying asks the journal, it never mints a resend.
      setError(caught);
    } finally {
      inflight.current.delete(ticket);
      setBusy("");
    }
  }
  return {
    error,
    run,
    outcome,
    busy: (ticket: string) => busy === ticket,
    held: (ticket: string) => heldOperation(action, accountId, ticket) != null,
  };
}
