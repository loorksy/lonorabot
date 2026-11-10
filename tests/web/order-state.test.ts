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

test("a partial fill reads «منفَّذ جزئيًا» with the broker's quantity and price (Q30)", () => {
  const partial = row("confirmed", {
    verification_status: "verified",
    request: { action: "buy", volume: "0.5" },
    result: { details: { price: "2346.40", volume: "0.3" } },
  });
  assert.equal(orderState(partial), "partial");
  assert.deepEqual(orderFill(partial), { price: "2346.40", volume: "0.3" });
  const full = row("confirmed", {
    verification_status: "verified",
    request: { action: "buy", volume: "0.5" },
    result: { details: { price: "2346.40", volume: "0.5" } },
  });
  assert.equal(orderState(full), "filled");
});
