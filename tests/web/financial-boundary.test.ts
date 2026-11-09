import assert from "node:assert/strict";
import test from "node:test";
import {
  financialBoundaryError,
  operationStatusKey,
  operationStatusText,
} from "../../packages/core/src/financial-boundary";

test("a broker-state resolution says what was observed, never that a live target is gone", () => {
  const resolved = (basis?: string, source = "broker_state") =>
    operationStatusKey("resolved", { resolution: { source, ...(basis ? { basis } : {}) } });
  assert.equal(resolved("target_closed"), "resolved_position_closed");
  assert.equal(resolved("target_no_longer_pending"), "resolved_order_gone");
  assert.equal(resolved("target_changed"), "resolved_target_changed");
  assert.equal(resolved(undefined), "resolved_unconfirmed");
  assert.equal(resolved(undefined, "owner"), "resolved_by_owner");
  const changed = operationStatusText(
    "resolved",
    { resolution: { source: "broker_state", basis: "target_changed" } },
    "en",
  );
  assert.ok(!changed.includes("no longer exists") && changed.includes("current state observed"));
  assert.ok(operationStatusText("resolved", {}, "ar").startsWith("سُوّيت"));
});

test("only server evidence promotes a stage; a never-sent failure reads Not sent", () => {
  assert.equal(operationStatusKey("failed", { send_state: "not_sent" }), "not_sent");
  assert.equal(operationStatusKey("failed", {}), "failed");
  assert.equal(
    operationStatusKey("confirmed", { verification: { status: "pending" } }),
    "awaiting_broker",
  );
  assert.equal(
    operationStatusKey("confirmed", { verification: { status: "unverified" } }),
    "acknowledged_unverified",
  );
  assert.equal(
    operationStatusKey("confirmed", { verification: { status: "verified" } }),
    "confirmed",
  );
  assert.equal(operationStatusKey("ambiguous"), "uncertain");
  assert.equal(operationStatusKey("reserved"), "preparing");
  assert.equal(operationStatusText("failed", { send_state: "not_sent" }, "en"), "Not sent");
});

test("boundary blocks explain why nothing was sent, in both languages, never a raw code", () => {
  const codes = [
    "trading_restriction_active",
    "broker_reconciliation_required",
    "broker_observation_unavailable",
    "risk_trade_limit",
    "risk_stop_loss_required",
    "risk_open_limit",
    "risk_open_unbounded",
    "risk_daily_loss_limit",
    "risk_free_margin_floor",
    "risk_limit_currency_mismatch",
    "risk_economics_unavailable",
    "risk_daily_history_incomplete",
    "risk_daily_history_unavailable",
    "risk_daily_history_invalid",
    "batch_halted_after_unconfirmed_result",
    "target_state_not_reached",
    "order_filled_before_cancel",
    "restriction_not_found",
    "restriction_window_invalid",
    "restriction_time_zone_required",
    "restriction_owner_manual_agent_conflict",
    "restriction_valid_until_required",
    "restriction_window_too_long",
    "restriction_account_required",
    "delete_blocked_unresolved_operation",
  ];
  for (const code of codes) {
    const en = financialBoundaryError(code, "en");
    const ar = financialBoundaryError(code, "ar-SA");
    assert.ok(en && ar && en !== ar, code);
    assert.ok(!en.includes(code) && !ar.includes(code), code);
  }
  // The account observation failing is not blamed on a previous operation.
  assert.ok(!financialBoundaryError("broker_observation_unavailable", "en")?.includes("previous"));
  assert.ok(!financialBoundaryError("broker_reconciliation_required", "en")?.includes("new order"));
  assert.equal(financialBoundaryError("unknown_code", "en"), null);
  assert.equal(financialBoundaryError(undefined, "en"), null);
});
