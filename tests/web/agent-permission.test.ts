import assert from "node:assert/strict";
import test from "node:test";
import type { AccountAuthority } from "@lonora/contracts";
import { authorityActions } from "@lonora/contracts";
import {
  customizedManagementProposal,
  emptyManagementCustomization,
  permissionFromAuthority,
} from "../../packages/core/src/agent-permission";
import { agentPermissionError } from "../../packages/core/src/agent-permission-errors";

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

test("all existing actions, optional limits and durations map to the signed contract", () => {
  const draft = emptyManagementCustomization();
  assert.deepEqual(draft.actions, authorityActions);
  draft.limits = {
    maximum_order_volume: "0.25",
    maximum_symbol_volume: "1.50",
    maximum_positions: "100",
    maximum_pending_orders: "0",
    maximum_actions: "10000",
    minimum_equity: "9999.99",
  };
  draft.allow_manual_positions = false;
  for (const [duration, hours] of [
    ["12h", 12],
    ["24h", 24],
    ["7d", 168],
  ] as const) {
    draft.duration = duration;
    const proposal = customizedManagementProposal(draft, scope, now);
    assert.ok(proposal);
    assert.equal(Date.parse(proposal.valid_until as string), now + hours * 3600000);
    assert.equal(proposal.maximum_order_volume, "0.25");
    assert.equal(proposal.maximum_symbol_volume, "1.50");
    assert.equal(proposal.maximum_positions, 100);
    assert.equal(proposal.maximum_pending_orders, 0);
    assert.equal(proposal.maximum_actions, 10000);
    assert.equal(proposal.minimum_equity, "9999.99");
    assert.equal(proposal.allow_manual_positions, false);
    assert.deepEqual(proposal.actions, authorityActions);
  }
  draft.duration = "until_stopped";
  const account = customizedManagementProposal(
    draft,
    { ...scope, symbol_scope: "account", symbols: [] },
    now,
  );
  assert.ok(account);
  assert.equal(account.symbol_scope, "account");
  assert.deepEqual(account.symbols, []);
  assert.equal(account.valid_until, null);
});

test("invalid numbers and dates cannot reach review and decimals retain exact precision", () => {
  for (const [field, values] of [
    ["maximum_order_volume", ["0", "-1", "NaN", "Infinity", "1e3", " 1", ".5", "1."]],
    ["maximum_positions", ["0", "101", "1.1", "9007199254740993"]],
    ["maximum_pending_orders", ["-1", "101", "0.1"]],
    ["maximum_actions", ["0", "10001"]],
    ["minimum_equity", ["0.000", "-10"]],
  ] as const) {
    for (const value of values) {
      const draft = emptyManagementCustomization();
      draft.limits[field] = value;
      assert.equal(customizedManagementProposal(draft, scope, now), null, `${field}: ${value}`);
    }
  }
  const draft = emptyManagementCustomization();
  draft.limits.maximum_order_volume = "1.000000000000000002";
  draft.limits.maximum_symbol_volume = "1.000000000000000001";
  assert.equal(customizedManagementProposal(draft, scope, now), null);
  draft.limits.maximum_symbol_volume = "0001.0000000000000000020";
  assert.ok(customizedManagementProposal(draft, scope, now));
  draft.duration = "7d";
  for (const invalid of [Number.NaN, Number.POSITIVE_INFINITY, 8640000000000000]) {
    assert.equal(customizedManagementProposal(draft, scope, invalid), null);
  }
});

test("proposal scope is isolated from later draft edits", () => {
  const draft = emptyManagementCustomization();
  const selected = { ...scope, symbols: ["XAUUSDm"] };
  const proposal = customizedManagementProposal(draft, selected, now);
  assert.ok(proposal);
  selected.symbols.push("EURUSD");
  draft.actions.pop();
  assert.deepEqual(proposal.symbols, ["XAUUSDm"]);
  assert.deepEqual(proposal.actions, authorityActions);
});

test("permission failures explain the required action in the selected language", () => {
  for (const code of [
    "agent_analysis_only",
    "trade_approval_required",
    "account_authority_unavailable",
    "account_authority_scope_mismatch",
    "account_authority_volume_limit",
    "agent_permission_state_invalid",
  ]) {
    const en = agentPermissionError(code, "en");
    const ar = agentPermissionError(code, "ar-SA");
    assert.ok(en && ar && en !== ar);
    assert.match(ar, /[\u0600-\u06ff]/);
    assert.ok(!en.includes(code) && !ar.includes(code));
  }
  assert.equal(agentPermissionError("unrelated_error", "en"), null);
  assert.equal(agentPermissionError("__proto__", "en"), null);
});
