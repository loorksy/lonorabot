import assert from "node:assert/strict";
import { test } from "node:test";
import type { AccountAuthority, DeviceChallenge, DeviceProof } from "../../packages/contracts/src";
import {
  activateAccountAuthority,
  authorityProposal,
  authorityStatus,
  emptyAuthorityDraft,
  fullManagementProposal,
} from "../../packages/core/src/account-authority";

const now = Date.now();
const scope = {
  thread_id: "conversation",
  account_id: "broker-account",
  symbols: ["EURUSD.demo"],
  actions: ["buy" as const],
  allow_manual_positions: false,
};
const draft = {
  maximum_order_volume: "0.10",
  maximum_symbol_volume: "0.30",
  maximum_positions: "3",
  maximum_pending_orders: "1",
  maximum_actions: "5",
  minimum_equity: "8000",
  valid_until: new Date(now + 3600000).toISOString(),
};
const proposal = authorityProposal(draft, scope, now);
assert.ok(proposal);
const pending: AccountAuthority = {
  id: "request",
  agent_id: "agent",
  thread_id: scope.thread_id,
  account_id: scope.account_id,
  status: "pending",
  envelope: {
    ...proposal,
    owner_id: "owner",
    agent_id: "agent",
    execution_mode: "live",
    schema_version: 1,
  },
  activation_expires_at: new Date(now + 600000).toISOString(),
  valid_until: draft.valid_until,
  created_at: new Date(now).toISOString(),
  updated_at: new Date(now).toISOString(),
  monetary_stop_risk: "unavailable",
};
test("permission is absent until explicit exact scope and every limit are supplied", () => {
  assert.equal(authorityProposal(emptyAuthorityDraft(), scope, now), null);
  assert.equal(authorityProposal(draft, { ...scope, symbols: [] }, now), null);
  assert.equal(authorityProposal(draft, { ...scope, actions: [] }, now), null);
  assert.equal(authorityProposal({ ...draft, maximum_order_volume: "0.40" }, scope, now), null);
  assert.equal(
    authorityProposal({ ...draft, valid_until: "2026-10-30T12:00:00" }, scope, now),
    null,
  );
  assert.deepEqual(proposal?.symbols, ["EURUSD.demo"]);
});
test("revocation stays terminal after expiry and pending signing has its own timeout", () => {
  assert.equal(authorityStatus({ ...pending, status: "revoked" }, now + 86400000), "revoked");
  assert.equal(authorityStatus(pending, now + 600001), "expired");
});
const challenge = {} as DeviceChallenge;
const proof = {} as DeviceProof;
function transport(result: AccountAuthority, calls: string[]) {
  return {
    async post<T>(path: string, _body: unknown): Promise<T> {
      calls.push(path);
      return (path.endsWith("/challenge") ? challenge : result) as T;
    },
  };
}
test("signing precedes server verification; no optimistic active result", async () => {
  const calls: string[] = [];
  const active = await activateAccountAuthority(
    transport({ ...pending, status: "active" }, calls),
    pending,
    async () => {
      calls.push("device-proof");
      return proof;
    },
  );
  assert.equal(active.status, "active");
  assert.deepEqual(calls, [
    "/account-authorities/request/challenge",
    "device-proof",
    "/account-authorities/verify",
  ]);
});
test("denied device proof never reaches verification", async () => {
  const calls: string[] = [];
  await assert.rejects(
    activateAccountAuthority(
      transport({ ...pending, status: "active" }, calls),
      pending,
      async () => {
        throw new Error("owner-cancelled");
      },
    ),
    /owner-cancelled/,
  );
  assert.deepEqual(calls, ["/account-authorities/request/challenge"]);
});
test("pending server result is never reported as activated", async () => {
  await assert.rejects(
    activateAccountAuthority(transport(pending, []), pending, async () => proof),
    /activation_unconfirmed/,
  );
});
test("different server scope or expanded limits fail closed", async () => {
  for (const changed of [
    { ...pending, status: "active" as const, account_id: "another-account" },
    {
      ...pending,
      status: "active" as const,
      envelope: { ...pending.envelope, maximum_actions: 999 },
    },
  ])
    await assert.rejects(
      activateAccountAuthority(transport(changed, []), pending, async () => proof),
      /scope_changed/,
    );
});

test("full management is an explicit proposal without default quotas, markets or expiry", () => {
  assert.equal(fullManagementProposal({ thread_id: "", account_id: "" }), null);
  const full = fullManagementProposal({ thread_id: scope.thread_id, account_id: scope.account_id });
  assert.ok(full);
  assert.equal(full.management_mode, "full");
  assert.equal(full.symbol_scope, "account");
  assert.deepEqual(full.symbols, []);
  assert.equal(full.maximum_order_volume, null);
  assert.equal(full.maximum_actions, null);
  assert.equal(full.valid_until, null);
  assert.equal(full.allow_manual_positions, true);
  const specialist = fullManagementProposal({ ...scope, symbol: "EXACT.suffix" });
  assert.deepEqual(specialist?.symbols, ["EXACT.suffix"]);
  assert.equal(specialist?.symbol_scope, "selected");
});
test("non-expiring permission requires explicit full mode and v2, with pending timeout retained", () => {
  const full = fullManagementProposal({ thread_id: scope.thread_id, account_id: scope.account_id });
  assert.ok(full);
  const active: AccountAuthority = {
    ...pending,
    status: "active",
    valid_until: null,
    envelope: {
      ...full,
      owner_id: "owner",
      agent_id: "agent",
      execution_mode: "live",
      schema_version: 2,
    },
  };
  assert.equal(authorityStatus(active, now + 365 * 86400000), "active");
  assert.equal(authorityStatus({ ...active, status: "pending" }, now + 600001), "expired");
  assert.equal(
    authorityStatus({ ...active, envelope: { ...active.envelope, schema_version: 1 } }, now),
    "expired",
  );
  assert.equal(authorityStatus({ ...active, status: "revoked" }, now), "revoked");
});
