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
  kind: "create_agent",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "agent",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 2,
  facts: { several_accounts: false },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-09T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T09:30:00Z",
  updated_at: "2026-11-08T09:30:00Z",
};
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
test("every pending card has its one-tap buttons in both languages", () => {
  for (const locale of ["en", "ar"]) {
    const pending = ownerActionCard(base, locale, now);
    assert.deepEqual(
      pending.buttons.map((button) => [button.key, button.decision]),
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

test("settled cards show what happened and offer no buttons", () => {
  const settled: Array<[Partial<OwnerAction>, string]> = [
    [{ status: "confirmed" }, "Agent created."],
    [{ status: "cancelled" }, "Dismissed. Nothing changed."],
    [{ status: "expired", status_reason: "expired" }, "This card expired. Nothing changed."],
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
  assert.deepEqual(en.lines.slice(0, 4), [
    "Account: ⁨Broker · 1234 · Live⁩",
    "Markets: ⁨XAUUSD⁩",
    "Opens, closes and manages trades",
    "Until you stop it",
  ]);
  // While pending the switch states the owner's own positions; no fixed line beside it.
  assert.ok(!en.lines.some((line) => line.startsWith("Positions you opened yourself")));
  assert.equal(
    en.options.find((option) => option.key === "stop:other-grant")?.label,
    "Stop ⁨Silver agent⁩ trading on its own on this account",
  );
  assert.ok(en.lines.some((line) => line.startsWith("⁨Silver agent⁩ already trades")));
  // The first grant card states the one rule; every grant card says what stays asked.
  assert.match(en.hint ?? "", /approval card/);
  assert.match(en.hint ?? "", /no agent, skill or plugin can ever widen your money authority/);
  assert.deepEqual(
    en.options.map((option) => [option.key, option.initial]),
    [
      ["manual", false],
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
  assert.match(ar.hint ?? "", /بطاقة موافقة/);
  assert.equal(ar.buttons[0]?.label, "التفويض بمفتاح المرور");
  // Amendment 1: no grant card offers to resume trading.
  assert.ok(!en.options.some((option) => option.key === "resume"));
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

test("Full delegation states what it means", () => {
  const card = fullCard();
  const en = ownerActionCard(card, "en", now);
  const full = en.options.find((option) => option.key === "delegation:full");
  assert.equal(full?.initial, true);
  assert.equal(
    full?.detail,
    "Full delegation: every pair on this account and every action (open, close fully or partly, pending orders, change stop loss and take profit, cancel), positions you opened yourself too, until you stop it.",
  );
  assert.equal(en.options.find((option) => option.key === "delegation:custom")?.initial, false);
  // Full always includes the owner's own positions: a line, never a switch.
  assert.ok(!en.options.some((option) => option.key === "manual"));
  assert.ok(en.lines.includes("Markets: All pairs on this account"));
  assert.ok(en.lines.includes("Opens, closes and manages trades"));
  assert.ok(en.lines.includes("Until you stop it"));
  assert.ok(en.lines.includes("Positions you opened yourself are included"));
  // The passkey still signs it; the challenge names Full and sends no own-positions switch.
  assert.equal(en.passkey, true);
  assert.equal(en.buttons[0]?.label, "Authorize with passkey");
  assert.deepEqual(ownerActionChoices(card, { manual: false }).challenge, { delegation: "full" });
  const ar = ownerActionCard(card, "ar", now);
  const arFull = ar.options.find((option) => option.key === "delegation:full");
  assert.match(arFull?.detail ?? "", /^تفويض كامل: كل أزواج هذا الحساب/);
  assert.ok(ar.lines.includes("يشمل المراكز التي فتحتها بنفسك"));
  // A signed Full delegation card says so in a line.
  const settled = ownerActionCard(
    { ...card, status: "confirmed", result: { delegation: "full" } },
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
      { ...grantCard({ grant }), status, result: { delegation: "custom" } },
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

test("Lonora's grant card preselects all pairs", () => {
  const card = grantCard({
    grant: {
      ...(grantCard().facts.grant ?? (undefined as never)),
      agent_name: "Lonora",
      agent_is_personal: true,
      symbol_scope: "account",
      symbols: [],
    },
    conflicts: [],
    first_grant: false,
  });
  const en = ownerActionCard(card, "en", now);
  assert.ok(en.lines.includes("Markets: All pairs on this account"));
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
    stop_authorities: [],
  });
  const chosen = ownerActionChoices(card, {
    manual: true,
    "stop:other-grant": true,
  });
  assert.deepEqual(chosen.challenge, { delegation: "custom", allow_manual_positions: true });
  assert.deepEqual(chosen.decision, {
    stop_authorities: ["other-grant"],
  });
  assert.deepEqual(ownerActionChoices(base, { manual: true }), { challenge: {}, decision: {} });
  const settled = ownerActionCard({ ...card, status: "confirmed", result: {} }, "en", now);
  assert.deepEqual(settled.options, []);
  assert.equal(settled.outcome, "Signed. It trades on its own inside this grant.");
  const covered = ownerActionCard(
    { ...card, status: "expired", status_reason: "grant_already_active" },
    "ar",
    now,
  );
  assert.equal(covered.outcome, "هذا موقّع بالفعل. لم يتغير شيء.");
  for (const code of ["owner_action_challenge_required", "owner_action_conflict_not_found"]) {
    assert.ok(ownerActionError(code, "en"));
    assert.match(ownerActionError(code, "ar") ?? "", /[؀-ۿ]/);
  }
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
      "equity floor ⁨1000⁩",
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
      result: { stopped_agents: ["Silver agent", "Copper agent"] },
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

test("no card resumes or starts trading, and no refusal names a Stop (amendment 1)", () => {
  for (const locale of ["en", "ar"] as const)
    for (const key of ["resume", "resumeTitle", "start", "startTitle", "signedStopped"])
      assert.ok(!(key in ownerActionLabels[locale]), key);
  for (const code of ["trading_not_started", "trading_disabled", "emergency_stop"])
    assert.equal(financialBoundaryError(code, "en"), null, code);
});

test("M5: a settled stop_tightened notice reads as applied, only an Undo reads as undone", async () => {
  const { noticeUndone } = await import("../../packages/core/src/owner-actions");
  assert.equal(noticeUndone({ kind: "stop_tightened", status: "confirmed" }), false);
  assert.equal(noticeUndone({ kind: "watch_changed", status: "confirmed" }), true);
  assert.equal(noticeUndone({ kind: "agent_created", status: "confirmed" }), true);
  assert.equal(noticeUndone({ kind: "agent_created", status: "pending" }), false);
});
