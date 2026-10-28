import assert from "node:assert/strict";
import test from "node:test";
import type { AccountAuthority } from "@lonora/contracts";
import {
  customizedManagementProposal,
  emptyManagementCustomization,
  permissionFromAuthority,
} from "../../packages/core/src/agent-permission";

const now = Date.parse("2026-10-28T12:00:00Z");
const scope = {
  thread_id: "thread",
  account_id: "account",
  symbol_scope: "selected" as const,
  symbols: ["XAUUSDm"],
};
test("customization uses full management with genuinely optional limits", () => {
  const draft = emptyManagementCustomization();
  draft.limits.maximum_pending_orders = "0";
  draft.limits.maximum_order_volume = "0.01";
  draft.duration = "12h";
  const proposal = customizedManagementProposal(draft, scope, now);
  assert.ok(proposal);
  assert.equal(proposal.management_mode, "full");
  assert.equal(proposal.maximum_pending_orders, 0);
  assert.equal(proposal.maximum_positions, null);
  assert.equal(proposal.maximum_order_volume, "0.01");
  assert.equal(proposal.minimum_equity, null);
  assert.equal(proposal.valid_until, "2026-10-29T00:00:00.000Z");
  assert.equal(
    customizedManagementProposal(emptyManagementCustomization(), scope, now)?.valid_until,
    null,
  );
});
test("invalid scopes, fractional counts and contradictory limits cannot reach review", () => {
  const draft = emptyManagementCustomization();
  draft.actions = [];
  assert.equal(customizedManagementProposal(draft, scope, now), null);
  draft.actions = ["buy", "buy"];
  assert.equal(customizedManagementProposal(draft, scope, now), null);
  draft.actions = ["buy"];
  draft.limits.maximum_positions = "1.5";
  assert.equal(customizedManagementProposal(draft, scope, now), null);
  draft.limits.maximum_positions = "1";
  draft.limits.maximum_order_volume = "2";
  draft.limits.maximum_symbol_volume = "1";
  assert.equal(customizedManagementProposal(draft, scope, now), null);
  assert.equal(
    customizedManagementProposal(emptyManagementCustomization(), { ...scope, symbols: [] }, now),
    null,
  );
  assert.equal(
    customizedManagementProposal(
      emptyManagementCustomization(),
      { ...scope, symbol_scope: "account" },
      now,
    ),
    null,
  );
});
test("bounded signed authority is autonomous; pending and expired requests are not", () => {
  const proposal = customizedManagementProposal(emptyManagementCustomization(), scope, now);
  assert.ok(proposal);
  const row = {
    status: "active",
    valid_until: null,
    envelope: { ...proposal, schema_version: 2 },
  } as AccountAuthority;
  assert.equal(permissionFromAuthority(row, now), "autonomous");
  const bounded = {
    ...row,
    valid_until: "2026-10-29T12:00:00Z",
    envelope: { ...row.envelope, management_mode: "bounded", schema_version: 1 },
  } as AccountAuthority;
  assert.equal(permissionFromAuthority(bounded, now), "autonomous");
  assert.equal(
    permissionFromAuthority(
      { ...bounded, status: "pending", activation_expires_at: "2026-10-28T12:05:00Z" },
      now,
    ),
    null,
  );
  assert.equal(permissionFromAuthority(bounded, now + 48 * 3600000), null);
  assert.equal(permissionFromAuthority({ ...row, status: "revoked" }, now), null);
});
