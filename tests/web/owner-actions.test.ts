import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { Message, OwnerAction } from "../../packages/contracts/src/index";
import { conversationTimeline } from "../../packages/core/src/conversation-timeline";
import { financialBoundaryError } from "../../packages/core/src/financial-boundary";
import {
  mergeOwnerAction,
  OWNER_ACTION_CHANGED,
  ownerActionCard,
  ownerActionChoices,
  ownerActionChoose,
  ownerActionError,
  ownerActionLabels,
  rereadOwnerAction,
} from "../../packages/core/src/owner-actions";
import { readinessTime } from "../../packages/core/src/trading-readiness";

const now = new Date("2026-11-08T10:00:00Z");
const base: OwnerAction = {
  id: "card",
  kind: "resume_trading",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "agent",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 2,
  facts: {
    several_accounts: false,
    global_trading: { state: "stopped", since: "2026-11-08T09:00:00Z", changed_by: "owner" },
  },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-09T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T09:30:00Z",
  updated_at: "2026-11-08T09:30:00Z",
};
const lift: OwnerAction = {
  ...base,
  kind: "lift_restriction",
  source: "system",
  facts: {
    several_accounts: true,
    account: { id: "acct", label: "Broker · 1234 · Live", provider: "metaapi" },
    restriction: {
      action_class: "no_new_entries",
      symbol: "XAUUSD",
      all_agents: true,
      agent_name: null,
      includes_owner_manual: false,
      state: "active",
      valid_from: "2026-11-08T08:00:00Z",
      valid_until: "2026-11-08T20:59:00Z",
      source: "agent",
      set_by_agent_name: "Gold agent",
    },
  },
};
const pause = lift.facts.restriction ?? (undefined as never);
const resolve: OwnerAction = {
  ...base,
  kind: "resolve_operation",
  source: "system",
  facts: {
    several_accounts: false,
    account: { id: "acct", label: null, provider: "simulation" },
    operation: {
      action: "buy",
      symbol: "XAUUSD",
      volume: "0.10",
      price: null,
      has_ticket: false,
      status: "ambiguous",
      submitted_at: "2026-11-08T09:02:00Z",
      by_agent_name: "Gold agent",
      by_owner: false,
    },
    blocks: "new_risk_on_this_symbol_or_ticket",
  },
};
const limits = (passkey: boolean): OwnerAction => ({
  ...base,
  kind: "set_account_limits",
  requires_passkey: passkey,
  facts: {
    several_accounts: false,
    account: { id: "acct", label: null, provider: "simulation" },
    current: {
      account_id: "acct",
      configured: true,
      currency: "USD",
      limits: { max_daily_loss: "300" },
      not_configured: [],
    },
    proposed: {
      account_id: "acct",
      configured: true,
      currency: "USD",
      limits: { max_daily_loss: passkey ? "900" : "200" },
      not_configured: [],
    },
    changes: [{ name: "max_daily_loss", from: "300", to: passkey ? "900" : "200" }],
  },
});

test("every pending card has its one-tap buttons in both languages", () => {
  for (const locale of ["en", "ar"]) {
    const resume = ownerActionCard(base, locale, now);
    assert.deepEqual(
      resume.buttons.map((button) => [button.key, button.decision]),
      [
        ["confirm", "confirm"],
        ["cancel", "cancel"],
      ],
    );
    const answer = ownerActionCard(resolve, locale, now);
    assert.deepEqual(
      answer.buttons.map((button) => [button.decision, button.outcome]),
      [
        ["confirm", "executed"],
        ["confirm", "not_executed"],
        ["confirm", "unknown"],
      ],
    );
    assert.equal(answer.notes, true);
    assert.equal(ownerActionCard(lift, locale, now).buttons.length, 2);
  }
  const en = ownerActionCard(resolve, "en", now);
  assert.equal(en.title, "The broker did not confirm this trade");
  assert.match(en.lines[0] ?? "", /^Market buy ⁨0\.10⁩ ⁨XAUUSD⁩ · at .+ · by ⁨Gold agent⁩$/);
  assert.match(en.hint ?? "", /will not be sent again/);
  assert.match(en.hint ?? "", /not as broker confirmation/);
  const ar = ownerActionCard(resolve, "ar", now);
  assert.equal(ar.title, "الوسيط لم يؤكد هذه الصفقة");
  assert.deepEqual(
    ar.buttons.map((button) => button.label),
    ["نُفذت", "لم تُنفذ", "غير معروفة — ارفع التعليق"],
  );
  // "Unknown" settles the card and releases the hold: the label and hint say so, so it
  // is never mistaken for "wait".
  assert.equal(en.buttons[2]?.label, "Unknown: release the hold");
  assert.match(en.hint ?? "", /any answer, Unknown included, releases this trade's hold/);
  assert.match(ar.hint ?? "", /وأي إجابة، ومنها «غير معروفة»، ترفع تعليق هذه الصفقة/);
  for (const locale of ["en", "ar"]) {
    const settled = ownerActionCard(
      { ...resolve, status: "confirmed", result: { outcome: "unknown" } },
      locale,
      now,
    );
    assert.match(settled.outcome ?? "", /no longer holds new risk|لم تعد تعلّق المخاطرة الجديدة/);
  }
});

test("a lift card names scope and source from facts, with tickers isolated in Arabic", () => {
  const en = ownerActionCard(lift, "en", now);
  assert.equal(en.title, "New entries paused");
  assert.equal(en.lines[0], "no new entries · ⁨XAUUSD⁩ · all agents · ⁨Broker · 1234 · Live⁩");
  assert.match(en.lines[1] ?? "", / · set by ⁨Gold agent⁩$/);
  assert.equal(en.hint, ownerActionLabels.en.exitsAllowed);
  const ar = ownerActionCard(lift, "ar", now);
  assert.equal(ar.title, "الصفقات الجديدة متوقفة");
  assert.match(ar.lines[0] ?? "", /⁨XAUUSD⁩/);
  assert.match(ar.lines[1] ?? "", /وضعه ⁨Gold agent⁩$/);
  const frozen = ownerActionCard(
    {
      ...lift,
      facts: {
        ...lift.facts,
        restriction: { ...pause, action_class: "all_mutations" },
      },
    },
    "en",
    now,
  );
  assert.equal(frozen.title, "Trading frozen");
  assert.equal(frozen.hint, ownerActionLabels.en.exitsFrozen);
});

test("raising a money limit asks for the passkey; lowering one is one tap", () => {
  const lower = ownerActionCard(limits(false), "en", now);
  assert.equal(lower.passkey, false);
  assert.equal(lower.buttons[0]?.label, "Apply");
  assert.equal(lower.lines[0], "Daily loss: ⁨300 USD⁩ → ⁨200 USD⁩");
  const raise = ownerActionCard(limits(true), "en", now);
  assert.equal(raise.passkey, true);
  assert.equal(raise.buttons[0]?.label, "Confirm with passkey");
  assert.equal(raise.hint, ownerActionLabels.en.limitsPasskey);
  // Arabic reads right to left, so the arrow points that way.
  assert.equal(
    ownerActionCard(limits(true), "ar", now).lines[0],
    "الخسارة اليومية: ⁨300 USD⁩ ← ⁨900 USD⁩",
  );
});

test("a limits card shows a moved trading day and currency, in both languages", () => {
  const moved = (locale: string, extra: OwnerAction["facts"]["changes"] = []) =>
    ownerActionCard(
      {
        ...limits(true),
        facts: {
          ...limits(true).facts,
          changes: [
            ...extra,
            { name: "trading_day_timezone", from: "UTC", to: "Pacific/Kiritimati" },
          ],
        },
      },
      locale,
      now,
    );
  const en = moved("en");
  assert.deepEqual(en.lines, ["Trading day starts at midnight in: ⁨UTC⁩ → ⁨Pacific/Kiritimati⁩"]);
  assert.equal(en.passkey, true);
  assert.equal(en.hint, "This can allow more risk, so it needs your passkey.");
  assert.deepEqual(moved("ar").lines, [
    "يبدأ يوم التداول عند منتصف الليل بتوقيت: ⁨UTC⁩ ← ⁨Pacific/Kiritimati⁩",
  ]);
  // A lower limit bundled with a moved day shows both lines, never only the reduction.
  const bundled = moved("en", [{ name: "max_daily_loss", from: "300", to: "290" }]);
  assert.deepEqual(bundled.lines, [
    "Daily loss: ⁨300 USD⁩ → ⁨290 USD⁩",
    "Trading day starts at midnight in: ⁨UTC⁩ → ⁨Pacific/Kiritimati⁩",
  ]);
  const currency = ownerActionCard(
    {
      ...limits(true),
      facts: { ...limits(true).facts, changes: [{ name: "currency", from: "USD", to: "EUR" }] },
    },
    "ar",
    now,
  );
  assert.deepEqual(currency.lines, ["العملة: ⁨USD⁩ ← ⁨EUR⁩"]);
  // Limits that moved on since the card was raised: it can only be dismissed.
  const stale = ownerActionCard(
    {
      ...limits(false),
      facts: { ...limits(false).facts, changes: undefined, no_longer_applies: true },
    },
    "en",
    now,
  );
  assert.equal(stale.passkey, false);
  assert.equal(stale.hint, ownerActionLabels.en.noLongerApplies);
  assert.deepEqual(
    stale.buttons.map((button) => button.decision),
    ["cancel"],
  );
});

test("settled cards show what happened and offer no buttons", () => {
  const settled: Array<[Partial<OwnerAction>, string]> = [
    [{ status: "confirmed" }, "Trading resumed."],
    [{ status: "cancelled" }, "Dismissed. Nothing changed."],
    [{ status: "expired", status_reason: "expired" }, "This card expired. Nothing changed."],
    [
      { status: "superseded", status_reason: "trading_already_running" },
      "Trading is already running.",
    ],
    [{ status: "superseded", status_reason: "done_by_another_card" }, "Done from another card."],
  ];
  for (const [change, line] of settled) {
    const spec = ownerActionCard({ ...base, ...change }, "en", now);
    assert.equal(spec.outcome, line);
    assert.deepEqual(spec.buttons, []);
    assert.equal(spec.hint, null);
  }
  const answered = ownerActionCard(
    { ...resolve, status: "confirmed", result: { outcome: "not_executed" } },
    "en",
    now,
  );
  assert.match(answered.outcome ?? "", /did not execute .*not broker confirmation/);
  const ended = ownerActionCard(
    { ...lift, status: "expired", status_reason: "restriction_already_ended" },
    "ar",
    now,
  );
  assert.equal(ended.outcome, "انتهى هذا الإيقاف مسبقًا. لم يتغير شيء.");
});

test("a late pending read never reopens a settled card", () => {
  const confirmed = { ...base, status: "confirmed" as const };
  assert.equal(mergeOwnerAction(confirmed, base).status, "confirmed");
  assert.equal(mergeOwnerAction(base, confirmed).status, "confirmed");
});

test("cards sit at their server anchor in the conversation", () => {
  const message = (id: string, seq: number): Message => ({
    id,
    seq,
    created_at: `2026-11-08T09:0${seq}:00Z`,
    thread_id: "thread",
    agent_id: "agent",
    role: "assistant",
    content: id,
    attachment_ids: [],
    reply_to: null,
  });
  const rows = conversationTimeline(
    [message("before", 1), message("after", 2)],
    [],
    [base, { ...base }],
  );
  assert.deepEqual(
    rows.map((row) => row.id),
    ["message:before", "owner_action:card", "message:after"],
  );
});

test("card refusals have owner text in both languages", () => {
  for (const code of [
    "owner_action_passkey_required",
    "owner_action_already_decided",
    "owner_action_expired_or_decided",
    "owner_action_outcome_required",
  ]) {
    assert.ok(ownerActionError(code, "en"));
    assert.match(ownerActionError(code, "ar") ?? "", /[؀-ۿ]/);
  }
  assert.equal(ownerActionError("unrelated", "en"), null);
});

test("Web and Mobile render the same shared spec and never show agent text", () => {
  for (const path of [
    "apps/web/src/components/owner-actions/OwnerActionCard.tsx",
    "apps/mobile/components/owner-action-card.tsx",
  ]) {
    const source = readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
    assert.match(source, /ownerActionCard\(row, locale\)/, path);
    assert.match(source, /\/owner-actions\/\$\{row\.id\}\/decision/, path);
    assert.doesNotMatch(source, /\.reason\b/, path);
    // A device registered from a card is named like every other enrollment.
    assert.match(source, /name: text\.deviceName/, path);
  }
  assert.equal(ownerActionLabels.en.deviceName, "My device");
  assert.equal(ownerActionLabels.ar.deviceName, "جهازي");
  assert.deepEqual(
    Object.keys(ownerActionLabels.en).sort(),
    Object.keys(ownerActionLabels.ar).sort(),
  );
});

const grantCard = (overrides: Partial<OwnerAction["facts"]> = {}): OwnerAction => ({
  ...base,
  kind: "grant_authority",
  requires_passkey: true,
  facts: {
    several_accounts: false,
    account: { id: "acct", label: "Broker · 1234 · Live", provider: "metaapi" },
    grant: {
      agent_name: "Gold agent",
      agent_is_personal: false,
      symbol_scope: "selected",
      symbols: ["XAUUSD"],
      actions: [
        "buy",
        "sell",
        "buy_limit",
        "sell_limit",
        "buy_stop",
        "sell_stop",
        "close_position",
        "modify_position",
        "cancel_order",
        "modify_order",
      ],
      all_actions: true,
      duration: "until_stopped",
      allow_manual_positions: false,
    },
    money: {
      limits: {
        account_id: "acct",
        configured: false,
        currency: null,
        limits: {},
        not_configured: [],
      },
      daily_loss: {
        current: null,
        proposed: "200.00",
        currency: "USD",
        basis: "requested",
        percent: "2",
      },
    },
    global_trading: { state: "stopped", since: null, changed_by: "default" },
    conflicts: [
      {
        authority_id: "other-grant",
        agent_name: "Silver agent",
        symbol_scope: "account",
        symbols: [],
      },
    ],
    replaces: null,
    first_grant: true,
    ...overrides,
  },
});

test("a grant card shows exactly what is signed, with the D1 defaults, in both languages", () => {
  const en = ownerActionCard(grantCard(), "en", now);
  assert.equal(en.title, "Let ⁨Gold agent⁩ trade on its own");
  assert.equal(en.passkey, true);
  assert.deepEqual(en.lines.slice(0, 5), [
    "Account: ⁨Broker · 1234 · Live⁩",
    "Markets: ⁨XAUUSD⁩",
    "Opens, closes and manages trades",
    "Until you stop it",
    "Daily loss limit: ⁨200.00 USD⁩ (⁨2%⁩ of equity)",
  ]);
  // While pending the switch states the owner's own positions; no fixed line beside it.
  assert.ok(!en.lines.some((line) => line.startsWith("Positions you opened yourself")));
  assert.equal(
    en.options.find((option) => option.key === "no_money_limit")?.label,
    "No money limit (my choice)",
  );
  assert.equal(
    en.options.find((option) => option.key === "stop:other-grant")?.label,
    "Stop ⁨Silver agent⁩ trading on its own on this account",
  );
  assert.ok(en.lines.includes("New trading is stopped"));
  assert.ok(en.lines.some((line) => line.startsWith("⁨Silver agent⁩ already trades")));
  // The first grant card states the one rule; every grant card says what stays asked.
  assert.match(en.hint ?? "", /approval card/);
  assert.match(en.hint ?? "", /no agent, skill or plugin can ever widen your money authority/);
  assert.deepEqual(
    en.options.map((option) => [option.key, option.initial]),
    [
      ["manual", false],
      ["no_money_limit", false],
      // Never started: Resume is pre-checked; after the owner's own Stop it is not.
      ["resume", true],
      ["stop:other-grant", false],
    ],
  );
  assert.deepEqual(
    en.buttons.map((button) => [button.key, button.decision, button.label]),
    [
      ["confirm", "confirm", "Authorize with passkey"],
      ["cancel", "cancel", "Not now"],
    ],
  );
  const ar = ownerActionCard(grantCard(), "ar", now);
  assert.equal(ar.title, "دع ⁨Gold agent⁩ يتداول بنفسه");
  assert.ok(ar.lines.includes("الأسواق: ⁨XAUUSD⁩"));
  assert.ok(ar.lines.includes("حد الخسارة اليومية: ⁨200.00 USD⁩ (⁨2%⁩ من حقوق الملكية)"));
  // A deliberate choice, not "optional".
  assert.equal(
    ar.options.find((option) => option.key === "no_money_limit")?.label,
    "بلا حد مالي، بقرار مني",
  );
  assert.match(ar.hint ?? "", /بطاقة موافقة/);
  assert.equal(ar.buttons[0]?.label, "التفويض بمفتاح المرور");
  const stopped = ownerActionCard(
    grantCard({ global_trading: { state: "stopped", since: null, changed_by: "owner" } }),
    "en",
    now,
  );
  assert.equal(stopped.options.find((option) => option.key === "resume")?.initial, false);
});

const fullCard = (overrides: Partial<OwnerAction["facts"]> = {}): OwnerAction => {
  const custom = grantCard().facts.grant ?? (undefined as never);
  return grantCard({
    grant: {
      ...custom,
      symbol_scope: "account",
      symbols: [],
      allow_manual_positions: true,
      delegation: "full",
      full_available: true,
    },
    money: {
      limits: {
        account_id: "acct",
        configured: true,
        currency: "USD",
        limits: { max_open_risk: "400" },
        not_configured: [],
      },
      daily_loss: {
        current: null,
        proposed: null,
        currency: "USD",
        basis: null,
        percent: null,
      },
    },
    conflicts: [],
    ...overrides,
  });
};

test("a grant card offers Custom or Full delegation in the same list, Custom selected", () => {
  const card = grantCard({
    grant: {
      ...(grantCard().facts.grant ?? (undefined as never)),
      delegation: "custom",
      full_available: true,
    },
  });
  const en = ownerActionCard(card, "en", now);
  // One choice inside the card's own list of options, never a separate button.
  assert.deepEqual(
    en.options.map((option) => [option.key, option.label, option.initial]),
    [
      ["delegation:custom", "Custom", true],
      ["delegation:full", "Full delegation", false],
      ["manual", "Include positions I opened myself", false],
      ["no_money_limit", "No money limit (my choice)", false],
      ["resume", "Resume trading too", true],
      ["stop:other-grant", "Stop ⁨Silver agent⁩ trading on its own on this account", false],
    ],
  );
  assert.deepEqual(
    en.buttons.map((button) => button.key),
    ["confirm", "cancel"],
  );
  // The selected choice says plainly what it means; the other one does not.
  assert.equal(en.options[0]?.detail, ownerActionLabels.en.customMeaning);
  assert.equal(en.options[1]?.detail, undefined);
  assert.deepEqual(ownerActionChoose(en.options[1] as never), {
    decision: "choose",
    delegation: "full",
  });
  assert.equal(ownerActionChoose(en.options[2] as never), null);
  // Custom keeps the D1 card exactly: the 2% daily loss line and the own-positions switch.
  assert.ok(en.lines.includes("Daily loss limit: ⁨200.00 USD⁩ (⁨2%⁩ of equity)"));
  // The challenge names the choice the card shows, so a changed card never signs it.
  assert.deepEqual(ownerActionChoices(card, {}).challenge, {
    delegation: "custom",
    allow_manual_positions: false,
  });
  const ar = ownerActionCard(card, "ar", now);
  assert.deepEqual(
    ar.options.slice(0, 2).map((option) => [option.label, option.initial]),
    [
      ["مخصص", true],
      ["تفويض كامل", false],
    ],
  );
  assert.match(ar.options[0]?.detail ?? "", /^مخصص: /);
  // A fixed-market agent's grant never covers every pair: no choice is offered.
  const fixed = grantCard({
    grant: { ...(card.facts.grant ?? (undefined as never)), full_available: false },
  });
  assert.ok(!ownerActionCard(fixed, "en", now).options.some((option) => option.choice));
});

test("Full delegation states what it means and that the account's limits stay", () => {
  const card = fullCard();
  const en = ownerActionCard(card, "en", now);
  const full = en.options.find((option) => option.key === "delegation:full");
  assert.equal(full?.initial, true);
  assert.equal(
    full?.detail,
    "Full delegation: every pair on this account and every action (open, close fully or partly, pending orders, change stop loss and take profit, cancel), positions you opened yourself too, until you stop it. This card sets no daily loss limit. Money limits you set on this account elsewhere stay in force; removing them is a separate step with your passkey.",
  );
  assert.equal(en.options.find((option) => option.key === "delegation:custom")?.initial, false);
  // Full always includes the owner's own positions: a line, never a switch; and the card
  // sets no daily loss limit, so it offers no opt-out of one.
  assert.ok(!en.options.some((option) => option.key === "manual"));
  assert.ok(!en.options.some((option) => option.key === "no_money_limit"));
  assert.ok(en.lines.includes("Markets: All pairs on this account"));
  assert.ok(en.lines.includes("Opens, closes and manages trades"));
  assert.ok(en.lines.includes("Until you stop it"));
  assert.ok(en.lines.includes("Positions you opened yourself are included"));
  assert.ok(!en.lines.some((line) => line.startsWith("Daily loss limit")));
  assert.ok(en.lines.includes(`Account money limits: Total open risk ${"⁨400 USD⁩"}`));
  // The passkey still signs it; the challenge names Full and sends no own-positions switch.
  assert.equal(en.passkey, true);
  assert.equal(en.buttons[0]?.label, "Authorize with passkey");
  assert.deepEqual(ownerActionChoices(card, { manual: false }).challenge, { delegation: "full" });
  // A switch ticked under Custom says nothing once Full is chosen.
  assert.equal(
    ownerActionChoices(card, { no_money_limit: true, keep_limit: true }).decision.money_limit,
    "apply",
  );
  const ar = ownerActionCard(card, "ar", now);
  const arFull = ar.options.find((option) => option.key === "delegation:full");
  assert.match(arFull?.detail ?? "", /^تفويض كامل: كل أزواج هذا الحساب/);
  assert.match(arFull?.detail ?? "", /خطوة منفصلة بمفتاح المرور\.$/);
  assert.ok(ar.lines.includes("يشمل المراكز التي فتحتها بنفسك"));
  // A signed Full delegation card says so in a line.
  const settled = ownerActionCard(
    { ...card, status: "confirmed", result: { delegation: "full", resumed: true } },
    "en",
    now,
  );
  assert.equal(settled.lines[0], "Full delegation");
  assert.deepEqual(settled.options, []);
  assert.equal(
    ownerActionCard(
      { ...card, status: "superseded", status_reason: "same_choice_on_another_card" },
      "ar",
      now,
    ).outcome,
    "التفويض نفسه ينتظر في بطاقة أخرى. لم يتغير شيء.",
  );
  for (const code of [
    "owner_action_full_delegation_unavailable",
    "owner_action_full_delegation_terms_fixed",
    "owner_action_delegation_required",
    OWNER_ACTION_CHANGED,
  ]) {
    assert.ok(ownerActionError(code, "en"));
    assert.match(ownerActionError(code, "ar") ?? "", /[؀-ۿ]/);
  }
});

test("a signed grant reads as Full delegation by its terms, as the readiness line does", () => {
  const custom = grantCard().facts.grant ?? (undefined as never);
  const terms = {
    ...custom,
    symbol_scope: "account" as const,
    symbols: [],
    all_actions: true,
    duration: "until_stopped" as const,
    allow_manual_positions: true,
    delegation: "custom" as const,
  };
  const signed = (grant: typeof terms, status: OwnerAction["status"]) =>
    ownerActionCard(
      { ...grantCard({ grant }), status, result: { delegation: "custom", resumed: true } },
      "en",
      now,
    ).lines;
  // Signed as Custom with exactly Full's terms: the card agrees with the status line.
  assert.equal(signed(terms, "confirmed")[0], "Full delegation");
  // Anything narrower is not Full delegation: one pair, own positions excluded, a time limit.
  for (const narrower of [
    { ...terms, symbol_scope: "selected" as const, symbols: ["XAUUSD"] },
    { ...terms, allow_manual_positions: false },
    { ...terms, duration: "24h" as const },
    { ...terms, all_actions: false, actions: ["close_position" as const] },
  ])
    assert.ok(!signed(narrower, "confirmed").includes("Full delegation"), JSON.stringify(narrower));
  // A Custom card the owner dismissed signed nothing: no Full delegation line.
  assert.ok(!signed(terms, "cancelled").includes("Full delegation"));
});

test("Web and Mobile send the delegation choice through the same decision route", () => {
  for (const path of [
    "apps/web/src/components/owner-actions/OwnerActionCard.tsx",
    "apps/mobile/components/owner-action-card.tsx",
  ]) {
    const source = readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
    assert.match(source, /ownerActionChoose\(option\)/, path);
    assert.match(source, /option\.detail/, path);
    // A card changed on another screen is read again before the owner taps again.
    assert.match(source, /code === OWNER_ACTION_CHANGED\) await reread\(\)/, path);
    assert.match(source, /rereadOwnerAction\(/, path);
  }
});

test("a card changed on another screen is read again from the conversation's cards", async () => {
  const stale = fullCard({
    grant: { ...(grantCard().facts.grant ?? (undefined as never)), delegation: "custom" },
  });
  const current = fullCard();
  const asked: string[] = [];
  const read = await rereadOwnerAction(async (path) => {
    asked.push(path);
    return [{ ...base, id: "other" }, current];
  }, stale);
  assert.deepEqual(asked, ["/owner-actions?thread_id=thread"]);
  assert.equal(read?.facts.grant?.delegation, "full");
  assert.equal(await rereadOwnerAction(async () => [], stale), null);
  // A card outside any conversation has nothing to read again from.
  assert.equal(await rereadOwnerAction(async () => [current], { ...stale, thread_id: null }), null);
  assert.equal(
    ownerActionError(OWNER_ACTION_CHANGED, "en"),
    "This card changed on another screen. It now shows the current choice; check it and tap again.",
  );
  assert.equal(
    ownerActionError(OWNER_ACTION_CHANGED, "ar"),
    "تغيّرت هذه البطاقة من شاشة أخرى، وهي تعرض الآن الاختيار الحالي؛ راجعها ثم اضغط مجددًا.",
  );
});

test("Lonora's grant card preselects all pairs; an existing limit is shown, never widened", () => {
  const card = grantCard({
    grant: {
      ...(grantCard().facts.grant ?? (undefined as never)),
      agent_name: "Lonora",
      agent_is_personal: true,
      symbol_scope: "account",
      symbols: [],
    },
    money: {
      limits: {
        account_id: "acct",
        configured: true,
        currency: "USD",
        limits: { max_daily_loss: "150" },
        not_configured: [],
      },
      daily_loss: {
        current: "150",
        proposed: null,
        currency: "USD",
        basis: "suggested",
        percent: "3",
      },
    },
    global_trading: { state: "running", since: null, changed_by: "owner" },
    conflicts: [],
    first_grant: false,
  });
  const en = ownerActionCard(card, "en", now);
  assert.ok(en.lines.includes("Markets: All pairs on this account"));
  // The account's own limit is shown once, as it is; no other line repeats it.
  assert.ok(en.lines.includes("Daily loss limit: ⁨150 USD⁩"));
  assert.ok(!en.lines.some((line) => line.startsWith("Account money limits: ")));
  assert.deepEqual(
    en.options.map((option) => option.key),
    ["manual"],
  );
  assert.doesNotMatch(en.hint ?? "", /plugin/);
});

test("a grant card's switches map to the signed challenge and the decision", () => {
  const card = grantCard();
  const initial = ownerActionChoices(card, {});
  assert.deepEqual(initial.challenge, { delegation: "custom", allow_manual_positions: false });
  assert.deepEqual(initial.decision, {
    money_limit: "apply",
    resume_trading: true,
    stop_authorities: [],
  });
  const chosen = ownerActionChoices(card, {
    manual: true,
    no_money_limit: true,
    resume: false,
    "stop:other-grant": true,
  });
  assert.deepEqual(chosen.challenge, { delegation: "custom", allow_manual_positions: true });
  assert.deepEqual(chosen.decision, {
    money_limit: "none",
    resume_trading: false,
    stop_authorities: ["other-grant"],
  });
  assert.deepEqual(ownerActionChoices(base, { resume: true }), { challenge: {}, decision: {} });
  const settled = ownerActionCard(
    { ...card, status: "confirmed", result: { resumed: true } },
    "en",
    now,
  );
  assert.deepEqual(settled.options, []);
  assert.equal(settled.outcome, "Signed. It trades on its own inside this grant.");
  // Signed without Resume while new trading is stopped: the line says it waits for Resume.
  const waiting = ownerActionCard({ ...card, status: "confirmed", result: {} }, "en", now);
  assert.equal(waiting.outcome, ownerActionLabels.en.signedStopped);
  const covered = ownerActionCard(
    { ...card, status: "expired", status_reason: "grant_already_active" },
    "ar",
    now,
  );
  assert.equal(covered.outcome, "هذا موقّع بالفعل. لم يتغير شيء.");
  for (const code of [
    "owner_action_challenge_required",
    "owner_action_conflict_not_found",
    "execution_policy_passkey_required",
  ]) {
    assert.ok(ownerActionError(code, "en"));
    assert.match(ownerActionError(code, "ar") ?? "", /[؀-ۿ]/);
  }
});

test("an existing daily loss limit is kept unless the owner asks for less, in one line", () => {
  const limits = (max: string, extra: Record<string, string> = {}) => ({
    account_id: "acct",
    configured: true,
    currency: "USD",
    limits: { max_daily_loss: max, ...extra },
    not_configured: [],
  });
  const money = (
    current: string,
    daily: Partial<NonNullable<OwnerAction["facts"]["money"]>["daily_loss"]>,
    extra: Record<string, string> = {},
  ): Partial<OwnerAction["facts"]> => ({
    money: {
      limits: limits(current, extra),
      daily_loss: {
        current,
        proposed: null,
        currency: "USD",
        basis: "suggested",
        percent: null,
        requested_above: null,
        ...daily,
      },
    },
  });
  // The owner's own 500 limit: no suggestion lowers it, the card shows it as it is.
  const kept = ownerActionCard(grantCard(money("500", {})), "en", now);
  assert.ok(kept.lines.includes("Daily loss limit: ⁨500 USD⁩"));
  assert.ok(!kept.lines.some((line) => line.startsWith("Account money limits")));
  assert.ok(!kept.options.some((option) => ["no_money_limit", "keep_limit"].includes(option.key)));
  // The owner's sentence asked for 300: one line from the current amount, and the
  // opt-out keeps the current limit.
  const lowered = grantCard(
    money(
      "500",
      { proposed: "300.00", basis: "requested", percent: "3" },
      { max_trade_risk: "50" },
    ),
  );
  const en = ownerActionCard(lowered, "en", now);
  assert.ok(en.lines.includes("Daily loss limit: ⁨500⁩ → ⁨300.00 USD⁩ (⁨3%⁩ of equity)"));
  assert.ok(en.lines.includes("Account money limits: Risk per trade ⁨50 USD⁩"), en.lines.join("|"));
  assert.ok(!en.lines.some((line) => line.includes("Daily loss ⁨500")));
  assert.equal(
    en.options.find((option) => option.key === "keep_limit")?.label,
    "Keep my current limit",
  );
  const ar = ownerActionCard(lowered, "ar", now);
  assert.ok(ar.lines.includes("حد الخسارة اليومية: ⁨500⁩ ← ⁨300.00 USD⁩ (⁨3%⁩ من حقوق الملكية)"));
  assert.equal(ar.options.find((option) => option.key === "keep_limit")?.label, "أبقِ حدي الحالي");
  assert.equal(ownerActionChoices(lowered, { keep_limit: true }).decision.money_limit, "none");
  assert.equal(ownerActionChoices(lowered, {}).decision.money_limit, "apply");
  // More than the current limit: the card keeps it and says how to raise it.
  const above = ownerActionCard(
    grantCard(money("500", { basis: "requested", requested_above: "800.00" })),
    "en",
    now,
  );
  assert.ok(above.lines.includes("Daily loss limit: ⁨500 USD⁩"));
  assert.ok(
    above.lines.some((line) =>
      line.startsWith("You asked for ⁨800.00 USD⁩: this card never raises the daily loss limit"),
    ),
  );
  const aboveAr = ownerActionCard(
    grantCard(money("500", { basis: "requested", requested_above: "800.00" })),
    "ar",
    now,
  );
  assert.ok(aboveAr.lines.some((line) => line.startsWith("طلبت ⁨800.00 USD⁩")));
  // Other limits but no daily loss yet: the opt-out names the daily loss only.
  const first = ownerActionCard(
    grantCard({
      money: {
        limits: {
          account_id: "acct",
          configured: true,
          currency: "USD",
          limits: { max_trade_risk: "50" },
          not_configured: [],
        },
        daily_loss: {
          current: null,
          proposed: "300.00",
          currency: "USD",
          basis: "suggested",
          percent: "3",
        },
      },
    }),
    "en",
    now,
  );
  assert.equal(
    first.options.find((option) => option.key === "no_money_limit")?.label,
    "No daily loss limit (my choice)",
  );
  assert.ok(first.lines.includes("Daily loss limit: ⁨300.00 USD⁩ (suggested: ⁨3%⁩ of equity)"));
});

test("replacing a capped grant names every cap, protection and market that changes", () => {
  const card = grantCard({
    replaces: {
      management_mode: "bounded",
      symbol_scope: "selected",
      symbols: ["XAUUSD", "EURUSD"],
      actions: ["buy", "sell", "close_position"],
      all_actions: false,
      maximum_order_volume: "0.5",
      maximum_symbol_volume: "1",
      maximum_positions: 3,
      maximum_pending_orders: 0,
      maximum_actions: 40,
      minimum_equity: "1000",
      valid_until: "2026-11-10T10:00:00Z",
      allow_manual_positions: true,
    },
    conflicts: [],
  });
  const en = ownerActionCard(card, "en", now);
  const line = en.lines.find((item) => item.startsWith("Replaces its current grant: ")) ?? "";
  const [before, after] = line.slice("Replaces its current grant: ".length).split(" → ");
  assert.equal(
    before,
    [
      "⁨XAUUSD⁩, ⁨EURUSD⁩",
      "Actions: Market buy, Market sell, Close position",
      "max ⁨0.5⁩ lots per order",
      "max ⁨1⁩ lots per market",
      "max ⁨3⁩ positions",
      "max ⁨0⁩ pending orders",
      "max ⁨40⁩ executions",
      "equity floor ⁨1000 USD⁩",
      "a stop loss on every entry, never loosened",
      `until ${readinessTime("2026-11-10T10:00:00Z", "en", now)}`,
      "positions you opened yourself included",
    ].join(" · "),
  );
  assert.equal(
    after,
    [
      "⁨XAUUSD⁩",
      "every trading action",
      "no volume, position or activity caps",
      "no stop-loss rule",
      "until you stop it",
    ].join(" · "),
  );
  // English lists use the English comma; Arabic keeps the Arabic comma.
  assert.ok(!line.includes("،"));
  const ar = ownerActionCard(card, "ar", now);
  const arLine = ar.lines.find((item) => item.startsWith("يحل محل تفويضه الحالي: ")) ?? "";
  assert.ok(arLine.includes("⁨XAUUSD⁩، ⁨EURUSD⁩"), arLine);
  assert.ok(arLine.includes(" ← "), arLine);
  assert.ok(arLine.includes("دون حدود للحجم أو الصفقات أو النشاط"), arLine);
  assert.ok(arLine.includes("حد حجم الأمر ⁨0.5⁩ لوت"), arLine);
});

test("a settled grant card names the agents it stopped and states the owner's own positions", () => {
  const settled = ownerActionCard(
    {
      ...grantCard(),
      status: "confirmed",
      result: { stopped_agents: ["Silver agent", "Copper agent"], resumed: true },
    },
    "en",
    now,
  );
  assert.equal(
    settled.outcome,
    "Signed. It trades on its own inside this grant. Stopped on this account: ⁨Silver agent⁩, ⁨Copper agent⁩.",
  );
  assert.ok(settled.lines.includes("Positions you opened yourself are excluded"));
  const ar = ownerActionCard(
    {
      ...grantCard(),
      status: "confirmed",
      result: { stopped_agents: ["Silver agent", "Copper agent"] },
    },
    "ar",
    now,
  );
  assert.match(ar.outcome ?? "", /⁨Silver agent⁩، ⁨Copper agent⁩/);
});

test("on a never-started install the resume card is Start trading, and says so when settled", () => {
  const first: OwnerAction = {
    ...base,
    facts: {
      several_accounts: false,
      global_trading: { state: "stopped", since: null, changed_by: "default" },
    },
  };
  for (const locale of ["en", "ar"] as const) {
    const text = ownerActionLabels[locale];
    const spec = ownerActionCard(first, locale, now);
    assert.equal(spec.title, text.startTitle);
    assert.equal(spec.buttons[0]?.label, text.start);
    assert.ok(spec.lines.includes(text.startStopped), spec.lines.join("|"));
    assert.equal(spec.hint, text.startHint);
    const done = ownerActionCard(
      { ...first, status: "confirmed", result: { started: true } },
      locale,
      now,
    );
    assert.equal(done.outcome, text.started);
  }
  // After the owner's own Stop it stays Resume.
  assert.equal(ownerActionCard(base, "en", now).buttons[0]?.label, ownerActionLabels.en.resume);
  assert.ok(financialBoundaryError("trading_not_started", "en")?.includes("Start trading"));
  assert.ok(financialBoundaryError("trading_not_started", "ar")?.includes("بدء التداول"));
});

test("M5: a settled stop_tightened notice reads as applied, only an Undo reads as undone", async () => {
  const { noticeUndone } = await import("../../packages/core/src/owner-actions");
  assert.equal(noticeUndone({ kind: "stop_tightened", status: "confirmed" }), false);
  assert.equal(noticeUndone({ kind: "watch_changed", status: "confirmed" }), true);
  assert.equal(noticeUndone({ kind: "agent_created", status: "confirmed" }), true);
  assert.equal(noticeUndone({ kind: "agent_created", status: "pending" }), false);
});
