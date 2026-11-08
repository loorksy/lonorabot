import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { Message, OwnerAction } from "../../packages/contracts/src/index";
import { conversationTimeline } from "../../packages/core/src/conversation-timeline";
import {
  mergeOwnerAction,
  ownerActionCard,
  ownerActionError,
  ownerActionLabels,
} from "../../packages/core/src/owner-actions";

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
