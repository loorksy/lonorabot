import assert from "node:assert/strict";
import test from "node:test";
import type { Journal } from "@lonora/contracts";
import { orderFill, orderState } from "../../apps/web/src/shell/agent/order-state";

const row = (status: Journal["status"], extra: Partial<Journal> = {}): Journal => ({
  operation_id: "op",
  account_id: "acct",
  status,
  request: {},
  result: {},
  submitted_at: null,
  updated_at: "2026-11-10T00:00:00Z",
  ...extra,
});

test("«منفَّذ» needs the broker's evidence or the owner's confirmation", () => {
  assert.equal(orderState(row("confirmed")), "accepted");
  assert.equal(orderState(row("confirmed", { verification_status: "verified" })), "filled");
  assert.equal(
    orderState(row("confirmed", { result: { details: { verification: { status: "verified" } } } })),
    "filled",
  );
  assert.equal(
    orderState(row("resolved", { resolution: { source: "owner", outcome: "executed" } })),
    "filled",
  );
  assert.equal(
    orderState(row("resolved", { resolution: { source: "owner", outcome: "not_executed" } })),
    "cancelled",
  );
  assert.equal(orderState(row("resolved")), "uncertain");
});

test("the other operation states map to the reference's names", () => {
  assert.equal(orderState(row("reserved")), "requested");
  assert.equal(orderState(row("submitted")), "sent");
  assert.equal(orderState(row("failed")), "rejected");
  assert.equal(orderState(row("ambiguous")), "uncertain");
});

// The journal row the executor writes for a MetaApi DONE_PARTIAL receipt: verify_effect
// never verifies a partial execution, so its verification stays pending.
const partialReceipt = (volume?: number): Journal =>
  row("confirmed", {
    request: { action: "buy", symbol: "XAUUSD", volume: "0.5", stop_loss: "2600" },
    result: {
      operation_id: "op",
      status: "confirmed",
      broker_id: "o2",
      code: "TRADE_RETCODE_DONE_PARTIAL",
      details: {
        partial_execution: true,
        numeric_code: 10010,
        order_id: "o2",
        position_id: "p2",
        price: 2701.5,
        ...(volume === undefined ? {} : { volume }),
        execution: { agent_id: "a1" },
        verification: { status: "pending", code: "broker_state_not_yet_verified" },
      },
    },
    verification_status: "pending",
    awaiting_broker_confirmation: true,
  });

test("a real partial fill reads «منفَّذ جزئيًا» with the broker's quantity when it gave one", () => {
  assert.equal(orderState(partialReceipt(0.3)), "partial");
  assert.deepEqual(orderFill(partialReceipt(0.3)), { price: "2701.5", volume: "0.3" });
  // No executed volume from the broker: still partial, without a number.
  assert.equal(orderState(partialReceipt()), "partial");
  assert.deepEqual(orderFill(partialReceipt()), { price: "2701.5", volume: null });
});

test("a placed limit or stop order is accepted, never filled, and shows no broker price", () => {
  for (const action of ["buy_limit", "sell_stop"]) {
    const placed = row("confirmed", {
      verification_status: "verified",
      request: { action, volume: "0.5", price: "215" },
      result: { details: { order_id: "o3", price: null } },
    });
    assert.equal(orderState(placed), "accepted");
    assert.deepEqual(orderFill(placed), { price: null, volume: null });
  }
  const rejected = row("failed", {
    request: { action: "buy_stop", volume: "0.1", price: "220" },
    result: { details: {} },
  });
  assert.deepEqual(orderFill(rejected), { price: null, volume: null });
});
