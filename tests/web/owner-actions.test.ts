import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { Message, OwnerAction } from "../../packages/contracts/src/index";
import {
  conversationTimeline,
  SLOT_OWNER_ACTION_KINDS,
} from "../../packages/core/src/conversation-timeline";
import { financialBoundaryError } from "../../packages/core/src/financial-boundary";
import {
  brokerCardFailed,
  mergeOwnerAction,
  ownerActionCard,
  ownerActionError,
  ownerActionLabels,
  ownerActionStatus,
} from "../../packages/core/src/owner-actions";

const now = new Date("2026-11-08T10:00:00Z");
const base: OwnerAction = {
  id: "card",
  kind: "supervision_paused",
  status: "pending",
  status_reason: null,
  source: "system",
  agent_id: "agent",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 2,
  facts: {
    several_accounts: false,
    supervision: {
      supervisor_name: "Lonora",
      supervised_names: ["Gold agent"],
      active: true,
      target: "agent",
      target_label: null,
      from_owner_message: false,
      owner_holds: false,
    },
  },
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
  kind: "settle_operation",
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
    // Settle Uncertain Operation: exactly these three answers, no free-text fields (10.3).
    assert.equal("notes" in answer, false);
  }
  // v38: the kind in the head, the broker's silence as the card's title, then the operation.
  const en = ownerActionCard(resolve, "en", now);
  assert.equal(en.title, "Unconfirmed operation");
  assert.equal(en.lines[0], "The broker did not confirm this trade");
  assert.match(en.lines[1] ?? "", /^Market buy ⁨0\.10⁩ ⁨XAUUSD⁩ · at .+ · by ⁨Gold agent⁩$/);
  // The hold the server keeps while the outcome is unknown (admission) stays said, in the
  // safety capsule's own words, and exits stay allowed (6).
  assert.equal(
    en.hint,
    "It will not be sent again. New risk on this market is held until it settles; exits stay allowed. Your answer is recorded as your statement, not as broker confirmation.",
  );
  const ar = ownerActionCard(resolve, "ar", now);
  // One spelling with the status line and the capsule (agent-status).
  assert.equal(ar.title, "عملية غير مؤكَّدة");
  assert.equal(ar.lines[0], "الوسيط لم يؤكد هذه الصفقة");
  assert.equal(
    ar.hint,
    "لن تُرسل مجددًا. المخاطرة الجديدة على هذا السوق معلّقة حتى تُحسم؛ يبقى الخروج متاحًا. تُسجَّل إجابتك كتصريح منك، لا كتأكيد من الوسيط.",
  );
  assert.deepEqual(
    ar.buttons.map((button) => button.label),
    ["نُفذت", "لم تُنفذ", "غير معروفة"],
  );
  assert.equal(en.buttons[2]?.label, "Unknown");
  // Unknown: the outcome stays unknown, the broker is still checked, nothing is resent.
  for (const [locale, line] of [
    [
      "en",
      "Recorded: the outcome stays unknown and the broker is still checked. It will not be sent again.",
    ],
    ["ar", "سُجّل: تبقى النتيجة غير معروفة ويُراجَع الوسيط، ولن تُرسل مجددًا."],
  ]) {
    const settled = ownerActionCard(
      { ...resolve, status: "confirmed", result: { outcome: "unknown" } },
      locale,
      now,
    );
    assert.equal(settled.outcome, line);
  }
});

test("settled cards show what happened and offer no buttons", () => {
  const settled: Array<[Partial<OwnerAction>, string]> = [
    [{ status: "confirmed" }, "Resumed."],
    [{ status: "cancelled" }, "Kept paused."],
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
    "trade_approval_already_decided",
    "trade_approval_run_unavailable",
    "trade_approval_not_found",
  ]) {
    assert.ok(ownerActionError(code, "en"));
    assert.match(ownerActionError(code, "ar") ?? "", /[؀-ۿ]/);
  }
  assert.equal(ownerActionError("unrelated", "en"), null);
});

test("a Trade Approval tap the server refuses never says «try again» on money", () => {
  assert.equal(
    ownerActionError("trade_approval_already_decided", "ar"),
    "سبقت الإجابة على هذا الطلب.",
  );
  assert.equal(
    ownerActionError("trade_approval_already_decided", "en"),
    "This request was already answered.",
  );
  assert.equal(
    ownerActionError("trade_approval_run_unavailable", "ar"),
    "لم يعد هذا الطلب بانتظارك. لم يُرسل شيء.",
  );
  for (const code of [
    "trade_approval_already_decided",
    "trade_approval_run_unavailable",
    "trade_approval_not_found",
  ])
    for (const locale of ["en", "ar"])
      assert.doesNotMatch(ownerActionError(code, locale) ?? "", /try again|حاول مرة أخرى/i);
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

test("no card resumes or starts trading, and no refusal names a Stop (amendment 1)", () => {
  for (const locale of ["en", "ar"] as const)
    for (const key of ["resume", "resumeTitle", "start", "startTitle", "signedStopped"])
      assert.ok(!(key in ownerActionLabels[locale]), key);
  for (const code of ["trading_not_started", "trading_disabled", "emergency_stop"])
    assert.equal(financialBoundaryError(code, "en"), null, code);
});

test("the Mandate card says a signed grant still applies within its own terms", () => {
  const mandate: OwnerAction = {
    ...base,
    kind: "trading_mode",
    facts: {
      several_accounts: false,
      trading_mode: "ask",
      agent: { exists: true, id: "agent", name: "Gold" },
    },
  } as OwnerAction;
  const plain = ownerActionCard(mandate, "ar", now);
  assert.ok(!plain.lines.includes(ownerActionLabels.ar.mandateGrantStays));
  for (const locale of ["ar", "en"] as const) {
    const granted = ownerActionCard(
      { ...mandate, facts: { ...mandate.facts, active_grant: true } } as OwnerAction,
      locale,
      now,
    );
    assert.ok(granted.lines.includes(ownerActionLabels[locale].mandateGrantStays));
  }
});

test("the migration's Mandate card names the agent's old grant in one line (14.3.18.2)", () => {
  const account = { id: "acc", label: "IC Markets · 5001", provider: "metaapi" };
  const mandate: OwnerAction = {
    ...base,
    kind: "trading_mode",
    facts: {
      several_accounts: false,
      trading_mode: "ask",
      agent: { exists: true, id: "agent", name: "Gold" },
    },
  } as OwnerAction;
  const named = (facts: Record<string, unknown>, locale: "ar" | "en") => {
    const text = ownerActionLabels[locale];
    const lines = ownerActionCard(
      { ...mandate, facts: { ...mandate.facts, ...facts } } as OwnerAction,
      locale,
      now,
    ).lines;
    const prefix = text.mandatePreviousGrant.split("{grant}")[0] ?? "";
    const found = lines.filter((line) => line.startsWith(prefix));
    assert.equal(found.length, 1, lines.join("|"));
    return found[0] ?? "";
  };
  const without = ownerActionCard(mandate, "ar", now).lines;
  const arPrefix = ownerActionLabels.ar.mandatePreviousGrant.split("{grant}")[0] ?? "";
  assert.ok(!without.some((line) => line.startsWith(arPrefix)), "no line without the fact");
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    const grant = { full_delegation: false, symbol_scope: "account", symbols: [], account };
    const full = named({ previous_grants: [{ ...grant, full_delegation: true }] }, locale);
    assert.ok(full.includes(text.mandatePreviousFull), full);
    assert.ok(!full.includes("IC Markets"), "one account: no account label");
    const wide = named({ previous_grants: [grant] }, locale);
    assert.ok(wide.includes(text.mandatePreviousAllPairs) && !wide.includes("()"), wide);
    const markets = named(
      {
        previous_grants: [{ ...grant, symbol_scope: "selected", symbols: ["XAUUSD", "EURUSD"] }],
        several_accounts: true,
      },
      locale,
    );
    assert.ok(markets.includes("⁨XAUUSD⁩") && markets.includes("⁨EURUSD⁩"), markets);
    assert.ok(markets.includes("IC Markets · 5001") && !markets.includes(text.mandatePreviousFull));
    // Two grants on two accounts: the plural line, one semicolon between the grants and the
    // list comma only between one grant's markets.
    const other = { id: "acc2", label: "Pepperstone · 7002", provider: "metaapi" };
    const lines = ownerActionCard(
      {
        ...mandate,
        facts: {
          ...mandate.facts,
          several_accounts: true,
          previous_grants: [
            { ...grant, symbol_scope: "selected", symbols: ["XAUUSD", "EURUSD"] },
            { ...grant, full_delegation: true, account: other },
          ],
        },
      } as OwnerAction,
      locale,
      now,
    ).lines;
    const singular = text.mandatePreviousGrant.split("{grant}")[0] ?? "";
    const plural = text.mandatePreviousGrants.split("{grants}")[0] ?? "";
    assert.ok(!lines.some((line) => line.startsWith(singular)), lines.join("|"));
    const [both, ...more] = lines.filter((line) => line.startsWith(plural));
    assert.ok(both && more.length === 0, lines.join("|"));
    const comma = locale === "ar" ? "، " : ", ";
    assert.deepEqual(
      both.slice(plural.length, both.lastIndexOf(")")).split(locale === "ar" ? "؛ " : "; "),
      [
        `⁨XAUUSD⁩${comma}⁨EURUSD⁩ · ⁨IC Markets · 5001⁩`,
        `${text.mandatePreviousFull} · ⁨Pepperstone · 7002⁩`,
      ],
    );
  }
});

test("a Settle card answered Unknown stays pending with Executed and Not executed live", () => {
  for (const locale of ["en", "ar"]) {
    const card = ownerActionCard({ ...resolve, result: { outcome: "unknown" } }, locale, now);
    assert.deepEqual(
      card.buttons.map((button) => button.outcome),
      ["executed", "not_executed"],
    );
    assert.match(card.lines.join(" "), /It will not be sent again\.|ولن تُرسل مجددًا\./);
  }
});

const broker: OwnerAction = {
  ...base,
  kind: "secret",
  status: "confirmed",
  facts: {
    several_accounts: false,
    secret: {
      label: "70000001 @ Exness-MT5Trial16",
      fields: [{ key: "PASSWORD", label: "Trading password", secret: true }],
      destination: "broker",
      agent_name: "Lonora",
      account: { login: "70000001", server: "Exness-MT5Trial16", platform: "mt5" },
    },
  },
};
const withPurpose = (purpose: "rotate_password" | "replace_token"): OwnerAction => ({
  ...broker,
  facts: {
    ...broker.facts,
    secret: { ...(broker.facts.secret as NonNullable<OwnerAction["facts"]["secret"]>), purpose },
  },
});

test("a saved broker card whose connection failed ends as a failure, never «Done»", () => {
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    // The production finding: «تعذّر الربط…» shown as a success.
    const failed = { ...broker, result: { provisioning: "failed" as const } };
    assert.equal(ownerActionCard(failed, locale, now).outcome, text.brokerFailed);
    assert.equal(brokerCardFailed(failed), true);
    assert.equal(brokerCardFailed({ ...broker, result: { provisioning: "connected" } }), false);
    for (const purpose of ["rotate_password", "replace_token"] as const)
      assert.equal(brokerCardFailed({ ...withPurpose(purpose), result: failed.result }), true);
    // Only a saved card: a pending or expired one is not a failed connection.
    assert.equal(brokerCardFailed({ ...failed, status: "expired" }), false);
  }
  // A Secret card never folds, so it never shows the folded line's chip: its frame says how
  // it ended (D3); the chip has no broker words left.
  for (const key of ["statusFailed", "statusSaved", "statusConnecting", "statusChanging"])
    assert.equal(Object.hasOwn(ownerActionLabels.ar, key), false, key);
});

test("every other card keeps the chip of its status", () => {
  const credential: OwnerAction = {
    ...broker,
    facts: {
      several_accounts: false,
      secret: {
        label: null,
        connect: "broker",
        fields: [],
        destination: "broker",
        agent_name: null,
      },
    },
  };
  const workspace: OwnerAction = {
    ...broker,
    facts: {
      several_accounts: false,
      secret: { label: "Keys", fields: [], destination: "workspace", agent_name: "Gold" },
    },
  };
  for (const locale of ["ar", "en"] as const) {
    const text = ownerActionLabels[locale];
    for (const [status, chip] of [
      ["pending", text.statusPending],
      ["confirmed", text.statusConfirmed],
      ["cancelled", text.statusCancelled],
      ["expired", text.statusExpired],
      ["superseded", text.statusSuperseded],
    ] as const)
      for (const card of [
        base,
        resolve,
        {
          ...base,
          kind: "trading_mode" as const,
          facts: {
            several_accounts: false,
            trading_mode: "ask",
            agent: { exists: true, id: "agent", name: "Gold" },
          },
        } as OwnerAction,
        workspace,
      ])
        assert.equal(
          ownerActionStatus({ ...card, status }, locale),
          chip,
          `${card.kind} ${status}`,
        );
    // A credential card converted by 0071 says what it connected, as before.
    assert.equal(
      ownerActionStatus({ ...credential, result: { provisioning: "failed" } }, locale),
      text.statusConfirmed,
    );
  }
  // A settled fixed card (Settle, Secret, Mandate: the kinds a slot names) is never folded
  // into a line (10.2.2, v38): it keeps its frame and shows the shared settled line inside it,
  // never a timer. Only a kind outside the five fixed cards folds into one line with the
  // shared chip, until W-AUTH and the team stack delete it.
  assert.deepEqual(Object.values(SLOT_OWNER_ACTION_KINDS).sort(), [
    "secret",
    "settle_operation",
    "trading_mode",
  ]);
  const source = readFileSync(
    new URL("../../apps/web/src/components/owner-actions/OwnerActionCard.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /\{spec\.outcome\}/);
  assert.match(source, /new Set<string>\(Object\.values\(SLOT_OWNER_ACTION_KINDS\)\)/);
  assert.match(source, /ownerActionFolds\(row\) && !inSheet/);
  assert.match(source, /ownerActionStatus\(row, i18n\.locale\)/);
  assert.doesNotMatch(source, /statusConfirmed|Countdown|oa-exp|expiresIn/);
  // A broker card whose connection failed never shows its outcome in the success tint.
  assert.match(source, /oa-done\$\{failed \? " bad" : ""\}/);
  assert.match(source, /const failed = brokerCardFailed\(row\)/);
  // «طلب جديد» and «عرض الأحدث» sit inside that frame.
  assert.match(source, /\{text\.renew\}/);
  assert.match(source, /\{text\.latest\}/);
  // Every fixed card keeps its frame and width in the conversation (v38 k-oa): a tapped
  // Mandate card, an approval and a receipt alike; an old kind's settled card is one line.
  const conversation = readFileSync(
    new URL("../../apps/web/src/conversation/Conversation.tsx", import.meta.url),
    "utf8",
  );
  assert.doesNotMatch(conversation, /cardKind="card"|OrderLine|\/trading\/journal/);
  assert.match(conversation, /cardKind=\{ownerActionFolds\(row\.action\) \? "line" : "oa"\}/);
});
