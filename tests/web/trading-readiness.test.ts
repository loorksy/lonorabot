import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { TradingReadiness } from "../../packages/contracts/src/trading";
import { financialBoundaryError } from "../../packages/core/src/financial-boundary";
import {
  isolate,
  moneyLimitsLine,
  tradingReadinessLine,
  tradingReadinessTone,
  tradingSafetyLabels,
} from "../../packages/core/src/trading-readiness";

const now = new Date("2026-11-08T10:00:00Z");
const base: TradingReadiness = {
  presentation_only: true,
  observed_at: now.toISOString(),
  state: "no_trading",
  params: {},
  level: "analysis",
  grants: [],
  global_trading: { state: "running", since: "2026-11-08T08:00:00Z", changed_by: "owner" },
  restrictions: [],
  money_limits: [],
  unresolved_operations: [],
  unresolved_count: 0,
  exits_allowed: true,
};
const states: Array<[TradingReadiness["state"], TradingReadiness["params"]]> = [
  ["no_trading", {}],
  ["agent_paused", {}],
  ["stopped", { since: "2026-11-08T09:00:00Z" }],
  [
    "paused",
    {
      action_class: "no_new_entries",
      valid_until: "2026-11-08T17:00:00Z",
      symbol: "XAUUSD",
      count: 1,
    },
  ],
  ["uncertain", { count: 2, symbol: "XAUUSD" }],
  ["ask_me", { money_limit_set: false }],
  [
    "on_its_own",
    {
      symbol_scope: "selected",
      symbols: ["XAUUSD", "EURUSD"],
      valid_until: null,
      grant_count: 1,
      money_limit_set: false,
    },
  ],
];

test("every readiness state has one plain line in English and Arabic, never a raw code", () => {
  for (const [state, params] of states) {
    const readiness = { ...base, state, params };
    const en = tradingReadinessLine(readiness, "en", now);
    const ar = tradingReadinessLine(readiness, "ar", now);
    assert.ok(en && ar && en !== ar, state);
    for (const line of [en, ar]) {
      // No snake_case code or wrapper reaches the owner.
      assert.ok(!line.includes("_"), `${state}: ${line}`);
      assert.ok(!line.includes("{") && !line.includes("undefined"), `${state}: ${line}`);
    }
    // Arabic first: Arabic text, with tickers isolated so they keep their order.
    assert.match(ar, /[؀-ۿ]/, state);
    if (JSON.stringify(params).includes("XAUUSD")) assert.ok(ar.includes(isolate("XAUUSD")), ar);
  }
  const stopped = { ...base, state: "stopped" as const, params: { since: null } };
  assert.equal(tradingReadinessLine(stopped, "en", now), "New trading stopped · exits allowed");
  assert.equal(tradingReadinessLine(stopped, "ar", now), "التداول الجديد متوقف · الخروج متاح");
  const own = { ...base, state: "on_its_own" as const, params: states[6][1] };
  assert.match(tradingReadinessLine(own, "en", now), /until you stop it · No money limit set$/);
  const account = { ...own, params: { ...own.params, symbol_scope: "account" as const } };
  assert.ok(tradingReadinessLine(account, "en", now).includes("All pairs on this account"));
  const limited = { ...own, params: { ...own.params, money_limit_set: true } };
  assert.ok(!tradingReadinessLine(limited, "en", now).includes("No money limit"));
});

test("the pill tone follows what is stopping or holding new trades", () => {
  const tone = (state: TradingReadiness["state"]) => tradingReadinessTone({ ...base, state });
  assert.equal(tone("on_its_own"), "ready");
  assert.equal(tone("ask_me"), "asks");
  assert.equal(tone("no_trading"), "idle");
  for (const held of ["stopped", "paused", "uncertain", "agent_paused"] as const)
    assert.equal(tone(held), "held");
});

test("money limits read as amounts, or say plainly that none is set", () => {
  const unset = {
    account_id: "account",
    configured: false,
    currency: null,
    limits: {},
    not_configured: ["max_daily_loss" as const],
  };
  assert.equal(moneyLimitsLine(unset, "en"), "No money limit set");
  assert.equal(moneyLimitsLine(unset, "ar"), "لا حد مالي محدد");
  const set = {
    ...unset,
    configured: true,
    currency: "USD",
    limits: { max_daily_loss: "300", max_trade_risk_equity_percent: "1" },
  };
  assert.equal(
    moneyLimitsLine(set, "en"),
    `Daily loss ${isolate("300 USD")} · Risk per trade, % of equity ${isolate("1%")}`,
  );
  assert.ok(moneyLimitsLine(set, "ar").startsWith("الخسارة اليومية"));
});

test("the brake and sheet labels exist in both languages with the same keys", () => {
  assert.deepEqual(
    Object.keys(tradingSafetyLabels.en).sort(),
    Object.keys(tradingSafetyLabels.ar).sort(),
  );
  for (const [key, value] of Object.entries(tradingSafetyLabels.ar))
    assert.ok(
      value && value !== tradingSafetyLabels.en[key as keyof typeof tradingSafetyLabels.en],
    );
  assert.equal(tradingSafetyLabels.en.stop, "Stop new trading");
  assert.equal(tradingSafetyLabels.ar.stop, "إيقاف الصفقات الجديدة");
});

test("Web and Mobile explain every brake and money-limit code from one shared table", () => {
  const codes = [
    "trading_disabled",
    "emergency_stop",
    "trading_restriction_active",
    "risk_daily_loss_limit",
    "risk_trade_limit",
    "risk_open_limit",
    "risk_open_unbounded",
    "risk_free_margin_floor",
    "risk_stop_loss_required",
    "risk_daily_history_unavailable",
    "risk_daily_history_incomplete",
    "risk_daily_history_invalid",
    "risk_economics_unavailable",
    "risk_limit_currency_mismatch",
  ];
  for (const code of codes) {
    const en = financialBoundaryError(code, "en");
    const ar = financialBoundaryError(code, "ar");
    assert.ok(en && ar && en !== ar && !en.includes(code) && !ar.includes(code), code);
  }
  // The one brake keeps exits and names its one-tap Resume, in both languages.
  for (const code of ["trading_disabled", "emergency_stop"]) {
    assert.ok(financialBoundaryError(code, "en")?.includes("Resume trading"), code);
    assert.ok(financialBoundaryError(code, "ar")?.includes("استئناف التداول"), code);
    assert.ok(financialBoundaryError(code, "en")?.includes("remain available"), code);
  }
  // Both clients route an API error code through the shared table before their own text.
  const web = readFileSync("apps/web/src/lib/user_error.ts", "utf8");
  const mobile = readFileSync("apps/mobile/lib/session.tsx", "utf8");
  for (const source of [web, mobile]) assert.ok(source.includes("financialBoundaryError("));
  assert.ok(!web.includes('case "trading_disabled"') && !web.includes('case "emergency_stop"'));
  // Approval results on both clients use the same table for their result codes.
  for (const file of [
    "apps/web/src/components/trading/TradeApprovals.tsx",
    "apps/mobile/components/trade-approval.tsx",
  ])
    assert.ok(readFileSync(file, "utf8").includes("financialBoundaryError(result.code"), file);
  // One brake on every client: Stop and Resume send the same single control change.
  const webTrading = readFileSync("apps/web/src/lib/trading.ts", "utf8");
  const mobilePill = readFileSync("apps/mobile/components/safety-pill.tsx", "utf8");
  for (const source of [webTrading, mobilePill]) {
    assert.ok(source.replace(/\s+/g, " ").includes("{ enabled: true, emergency_stop: false }"));
    assert.ok(source.replace(/\s+/g, " ").includes("{ enabled: false, emergency_stop: true }"));
  }
});
