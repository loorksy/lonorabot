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
    ["نُفذت", "لم تُنفذ", "لا أعرف بعد"],
  );
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
  }
  assert.deepEqual(
    Object.keys(ownerActionLabels.en).sort(),
    Object.keys(ownerActionLabels.ar).sort(),
  );
});
