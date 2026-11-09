import assert from "node:assert/strict";
import test from "node:test";
import {
  heldOperation,
  holdOperation,
  operationSettled,
  settleOperation,
} from "../../apps/web/src/lib/held-operation";

// The browser keeps held identities in sessionStorage; Node gets the same small store.
const stored = new Map<string, string>();
Object.assign(globalThis, {
  sessionStorage: {
    getItem: (name: string) => stored.get(name) ?? null,
    setItem: (name: string, value: string) => void stored.set(name, value),
    removeItem: (name: string) => void stored.delete(name),
  },
});

test("an unsettled operation keeps its identity for every retry", () => {
  const first = holdOperation("close_position", "account-1", "101");
  assert.equal(holdOperation("close_position", "account-1", "101"), first);
  for (const status of ["reserved", "submitted", "ambiguous"]) {
    assert.equal(operationSettled(status), false);
    assert.equal(settleOperation("close_position", "account-1", "101", status), false);
    assert.equal(heldOperation("close_position", "account-1", "101"), first);
  }
  // An unknown status is never treated as settled.
  assert.equal(settleOperation("close_position", "account-1", "101", "created"), false);
  assert.equal(holdOperation("close_position", "account-1", "101"), first);
});

for (const status of ["confirmed", "failed", "resolved"])
  test(`a ${status} operation releases its identity: the next click is a new operation`, () => {
    const ticket = `ticket-${status}`;
    const first = holdOperation("cancel_order", "account-1", ticket);
    assert.equal(stored.size > 0, true);
    assert.equal(operationSettled(status), true);
    assert.equal(settleOperation("cancel_order", "account-1", ticket, status), true);
    assert.equal(heldOperation("cancel_order", "account-1", ticket), null);
    // Releasing twice is a no-op, and the next action mints a different identity.
    assert.equal(settleOperation("cancel_order", "account-1", ticket, status), false);
    const next = holdOperation("cancel_order", "account-1", ticket);
    assert.notEqual(next, first);
  });

test("identities are per action, account and ticket", () => {
  const close = holdOperation("close_position", "account-2", "7");
  assert.notEqual(holdOperation("close_position", "account-3", "7"), close);
  assert.notEqual(holdOperation("cancel_order", "account-2", "7"), close);
  settleOperation("close_position", "account-3", "7", "resolved");
  assert.equal(heldOperation("close_position", "account-2", "7"), close);
});
