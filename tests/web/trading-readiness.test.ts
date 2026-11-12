import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { TradingReadiness } from "../../packages/contracts/src/trading";
import {
  financialBoundaryError,
  financialResultReason,
} from "../../packages/core/src/financial-boundary";
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
  restrictions: [],
  money_limits: [],
  unresolved_operations: [],
  unresolved_count: 0,
  exits_allowed: true,
};
const states: Array<[TradingReadiness["state"], TradingReadiness["params"]]> = [
  ["no_trading", {}],
  ["agent_paused", {}],
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
  const own = { ...base, state: "on_its_own" as const, params: states[5][1] };
  assert.match(tradingReadinessLine(own, "en", now), /until you stop it · No money limit set$/);
  const account = { ...own, params: { ...own.params, symbol_scope: "account" as const } };
  assert.ok(tradingReadinessLine(account, "en", now).includes("All pairs on this account"));
  const limited = { ...own, params: { ...own.params, money_limit_set: true } };
  assert.ok(!tradingReadinessLine(limited, "en", now).includes("No money limit"));
  // The daily loss limit signed with the grant is part of the line, in both languages.
  const daily = {
    ...own,
    params: {
      ...own.params,
      symbols: ["XAUUSD"],
      money_limit_set: true,
      daily_loss: { amount: "200.00", currency: "USD" },
    },
  };
  assert.equal(
    tradingReadinessLine(daily, "en", now),
    `Trades on its own · ${isolate("XAUUSD")} · until you stop it · Daily loss ${isolate("200.00 USD")}`,
  );
  assert.equal(
    tradingReadinessLine(daily, "ar", now),
    `يتداول باستقلال · ${isolate("XAUUSD")} · حتى توقفه · الخسارة اليومية ${isolate("200.00 USD")}`,
  );
  // Full delegation says so in place of the markets; the account's own limit still shows.
  const full = {
    ...daily,
    params: {
      ...daily.params,
      symbol_scope: "account" as const,
      symbols: [],
      full_delegation: true,
    },
  };
  assert.equal(
    tradingReadinessLine(full, "en", now),
    `Trades on its own · Full delegation · until you stop it · Daily loss ${isolate("200.00 USD")}`,
  );
  assert.equal(
    tradingReadinessLine(full, "ar", now),
    `يتداول باستقلال · تفويض كامل · حتى توقفه · الخسارة اليومية ${isolate("200.00 USD")}`,
  );
  // With several accounts the line names the granted one the way the sheet does ...
  const named = { ...daily, params: { ...daily.params, account_id: "acct-1", account_count: 1 } };
  assert.ok(
    tradingReadinessLine(named, "en", now, () => "Simulation · 1").startsWith(
      `Trades on its own · ${isolate("Simulation · 1")} · `,
    ),
  );
  // ... and grants on several accounts are counted; the sheet lists each with its limit.
  const two = { ...daily, params: { ...daily.params, account_count: 2 } };
  assert.equal(tradingReadinessLine(two, "en", now), "Trades on its own on 2 accounts");
  assert.equal(tradingReadinessLine(two, "ar", now), `يتداول باستقلال على ${isolate("2")} حسابات`);
});

test("the sheet's freeze alert says exits are blocked too, in English and Arabic", () => {
  assert.match(tradingSafetyLabels.en.exitsFrozen, /exits are blocked too/);
  assert.match(tradingSafetyLabels.ar.exitsFrozen, /الخروج محظور أيضًا/);
});

test("a pause names its account when the owner has several, and only then", () => {
  const paused = {
    ...base,
    state: "paused" as const,
    params: {
      action_class: "no_new_entries" as const,
      valid_until: null,
      symbol: null,
      account_id: "account-b",
      count: 1,
    },
  };
  const named = (id: string) => (id === "account-b" ? "Simulation · 2" : null);
  assert.equal(
    tradingReadinessLine(paused, "en", now),
    "Paused: no new entries · until you lift it",
  );
  assert.equal(
    tradingReadinessLine(paused, "en", now, named),
    `Paused (${isolate("Simulation · 2")}): no new entries · until you lift it`,
  );
  assert.equal(
    tradingReadinessLine(paused, "ar", now, named),
    `إيقاف (${isolate("Simulation · 2")}): لا صفقات جديدة · حتى ترفعه`,
  );
  const market = { ...paused, params: { ...paused.params, symbol: "XAUUSD" } };
  assert.equal(
    tradingReadinessLine(market, "en", now, named),
    `Paused on ${isolate("XAUUSD")} (${isolate("Simulation · 2")}): no new entries · until you lift it`,
  );
});

test("the pill tone follows what is stopping or holding new trades", () => {
  const tone = (state: TradingReadiness["state"]) => tradingReadinessTone({ ...base, state });
  assert.equal(tone("on_its_own"), "ready");
  assert.equal(tone("ask_me"), "asks");
  assert.equal(tone("no_trading"), "idle");
  for (const held of ["paused", "uncertain", "agent_paused"] as const)
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

test("the sheet labels exist in both languages with the same keys, and name no Stop", () => {
  assert.deepEqual(
    Object.keys(tradingSafetyLabels.en).sort(),
    Object.keys(tradingSafetyLabels.ar).sort(),
  );
  for (const [key, value] of Object.entries(tradingSafetyLabels.ar))
    assert.ok(
      value && value !== tradingSafetyLabels.en[key as keyof typeof tradingSafetyLabels.en],
    );
  // Amendment 1: Lonora has no Stop control, so no label offers Stop, Resume or Start.
  for (const key of ["stop", "resume", "start", "stopped", "running", "neverStarted"])
    assert.ok(!(key in tradingSafetyLabels.en) && !(key in tradingSafetyLabels.ar), key);
});

test("Web and Mobile explain every pause and money-limit code from one shared table", () => {
  const codes = [
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
  // Stop is gone: its codes have no owner text any more.
  for (const code of ["trading_disabled", "emergency_stop", "trading_not_started"])
    assert.equal(financialBoundaryError(code, "en"), null, code);
  // Both clients route an API error code through the shared table before their own text.
  const web = readFileSync("apps/web/src/lib/user_error.ts", "utf8");
  const mobile = readFileSync("apps/mobile/lib/session.tsx", "utf8");
  for (const source of [web, mobile]) assert.ok(source.includes("financialBoundaryError("));
  assert.ok(!web.includes('case "trading_disabled"') && !web.includes('case "emergency_stop"'));
  // Approval results on both clients use the same table for their result codes, through
  // the status-aware lookup (an uncertain result never reads as "not sent").
  for (const file of [
    "apps/web/src/components/trading/TradeApprovals.tsx",
    "apps/mobile/components/trade-approval.tsx",
  ])
    assert.ok(
      readFileSync(file, "utf8").includes("financialResultReason(result.status, result.code"),
      file,
    );
  assert.equal(
    financialResultReason("failed", "risk_daily_loss_limit", "en"),
    financialBoundaryError("risk_daily_loss_limit", "en"),
  );
  // No client sends a Stop or Resume: there is no trading control route any more.
  const webTrading = readFileSync("apps/web/src/lib/trading.ts", "utf8");
  const mobilePill = readFileSync("apps/mobile/components/safety-pill.tsx", "utf8");
  for (const source of [webTrading, mobilePill])
    assert.ok(!source.includes("/trading/controls") && !source.includes("emergency_stop"));
  // Both sheets name the agent that set a pause and the account of every item when
  // there are several (web: the conversation's AgentSheet).
  const mobileChecks = [
    "agentName(item.created_by_agent_id)",
    "accountName(item.account_id)",
    "accountName(operation.account_id)",
    "tradingReadinessLine(readiness, locale, new Date(), accountName)",
  ];
  for (const check of mobileChecks) assert.ok(mobilePill.includes(check), check);
  const webSheet = readFileSync("apps/web/src/conversation/sheets/AgentSheet.tsx", "utf8");
  for (const check of [
    "agentName(r.created_by_agent_id)",
    "accountName(r.account_id)",
    "accountName(op.account_id)",
    "tradingReadinessLine(readiness, i18n.locale, new Date(), accountName)",
  ])
    assert.ok(webSheet.includes(check), check);
});
