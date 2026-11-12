import assert from "node:assert/strict";
import test from "node:test";
import type { AgentLiveState, Journal } from "../../packages/contracts/src/index";
import { agentStatusLine, uncertainLine } from "../../packages/core/src/agent-status";
import { orderLineAction, orderLineState, orderLineText } from "../../packages/core/src/order-line";

const now = new Date("2026-11-08T10:00:00Z");
const idle: AgentLiveState = {
  agent_id: "gold",
  observed_at: now.toISOString(),
  state: "idle",
  phase: "idle",
  reason_code: null,
  pending_approval_count: 0,
  watch_count: 0,
  watches: [],
  tasks: [],
  health: [],
};
const watching: AgentLiveState = {
  ...idle,
  state: "waiting",
  phase: "monitoring",
  watch_count: 1,
  watches: [
    {
      id: "w",
      kind: "price",
      account_id: "acct",
      symbol: "XAUUSD",
      condition: "above",
      level: "2350",
      indicator: null,
      timeframe: null,
      metric: null,
      expires_at: null,
      lifecycle: "pending",
    },
  ],
  current_work: { kind: "watching", text: "XAUUSD", until: null, run_id: null },
};
const uncertain: AgentLiveState = {
  ...idle,
  state: "action_required",
  phase: "uncertain",
  trading_readiness: {
    presentation_only: true,
    observed_at: now.toISOString(),
    state: "uncertain",
    params: { count: 3 },
  },
};

test("the status line uses the reference's own words", () => {
  assert.equal(agentStatusLine(idle, "ar", now), "نشط");
  assert.equal(agentStatusLine({ ...idle, state: "paused", phase: "paused" }, "ar"), "متوقف مؤقتًا");
  assert.equal(agentStatusLine(uncertain, "ar"), "⁨3⁩ عمليات غير مؤكَّدة");
  assert.equal(agentStatusLine({ ...uncertain, trading_readiness: null }, "ar"), "عملية غير مؤكَّدة");
  assert.equal(uncertainLine(12, "ar"), "⁨12⁩ عملية غير مؤكَّدة");
  assert.equal(
    agentStatusLine({ ...idle, state: "action_required", pending_card_id: "card" }, "ar"),
    "بانتظار قرارك",
  );
  const broker = {
    ...idle,
    state: "action_required" as const,
    phase: "awaiting_broker",
    current_work: {
      kind: "broker" as const,
      text: "",
      operation: { action: "buy", volume: "0.10", symbol: "XAUUSD" },
      until: null,
      run_id: "r",
    },
  };
  assert.equal(agentStatusLine(broker, "ar"), "بانتظار تأكيد الوسيط");
  const analysing = {
    ...idle,
    state: "working" as const,
    phase: "thinking",
    current_work: { kind: "analysing" as const, text: "حلّل الذهب", until: null, run_id: "r" },
  };
  assert.equal(agentStatusLine(analysing, "ar"), "يحلّل");
  const searching = {
    ...analysing,
    current_work: { ...analysing.current_work, kind: "searching" as const },
  };
  assert.equal(agentStatusLine(searching, "ar"), "يبحث");
  assert.equal(agentStatusLine(searching, "en"), "Searching");
  assert.equal(
    agentStatusLine(
      { ...analysing, current_work: { ...analysing.current_work, kind: "other" } },
      "ar",
    ),
    "يعمل",
  );
  assert.equal(agentStatusLine(watching, "ar", now), "يراقب ⁨XAUUSD⁩");
});

test("the status line follows the reference priority, most urgent first", () => {
  const all: AgentLiveState = {
    ...watching,
    state: "action_required",
    phase: "uncertain",
    pending_card_id: "card",
    pending_approval_count: 1,
    current_work: {
      kind: "waiting_owner",
      text: "",
      card: "owner_action",
      until: null,
      run_id: null,
    },
  };
  // paused → uncertain operation → pending decision → order at the broker → work → watch.
  assert.equal(agentStatusLine({ ...all, state: "paused" }, "ar"), "متوقف مؤقتًا");
  assert.equal(agentStatusLine(all, "ar"), "عملية غير مؤكَّدة");
  assert.equal(agentStatusLine({ ...all, phase: "awaiting_broker" }, "ar"), "بانتظار قرارك");
  const noCard = { ...all, phase: "awaiting_broker", pending_card_id: null, current_work: null };
  assert.equal(
    agentStatusLine({ ...noCard, pending_approval_count: 0 }, "ar"),
    "بانتظار تأكيد الوسيط",
  );
  const working: AgentLiveState = {
    ...watching,
    state: "working",
    current_work: { kind: "analysing", text: "", until: null, run_id: "r" },
  };
  assert.equal(agentStatusLine(working, "ar"), "يحلّل");
});

test("the status line says «يعمل» or «ينتظر», never «نشط», when the server names no work", () => {
  // A run with no named family is the agent at work.
  const busy: AgentLiveState = { ...idle, state: "working", phase: "thinking" };
  assert.equal(agentStatusLine(busy, "ar"), "يعمل");
  assert.equal(agentStatusLine(busy, "en"), "Working");
  // A waiting agent, a model retry or a read retry included, waits: it is never «نشط».
  const waiting: AgentLiveState[] = [
    { ...idle, state: "waiting", phase: "queued" },
    { ...idle, state: "waiting", phase: "recovering", reason_code: "model_provider_retry" },
    { ...idle, state: "waiting", phase: "recovering", reason_code: "retry_backoff" },
  ];
  for (const state of waiting) {
    assert.equal(agentStatusLine(state, "ar"), "ينتظر");
    assert.equal(agentStatusLine(state, "en"), "Waiting");
  }
  // A service problem is said as it is, never as «نشط».
  const unwell: AgentLiveState = { ...idle, state: "degraded" };
  assert.notEqual(agentStatusLine(unwell, "ar"), "نشط");
});

function journal(status: Journal["status"], extra: Partial<Journal> = {}): Journal {
  return {
    operation_id: "op",
    account_id: "acct",
    status,
    request: { action: "buy", symbol: "XAUUSD", volume: "0.10" },
    result: {},
    submitted_at: null,
    updated_at: now.toISOString(),
    ...extra,
  };
}

test("an order line shows the server state under the reference's names", () => {
  assert.deepEqual(orderLineState(journal("reserved")).steps, ["requested"]);
  assert.equal(orderLineState(journal("submitted")).state, "sent");
  const filled = orderLineState(
    journal("confirmed", { result: { broker_id: "48301", details: { volume: "0.10" } } }),
  );
  assert.equal(filled.state, "filled");
  assert.deepEqual(filled.steps, ["requested", "sent", "accepted", "filled"]);
  assert.equal(filled.evidence, "broker");
  const partial = orderLineState(
    journal("confirmed", { result: { broker_id: "48301", details: { volume: "0.06" } } }),
  );
  assert.equal(partial.state, "partial");
  assert.equal(partial.filled_volume, "0.06");
  assert.equal(partial.requested_volume, "0.10");
  assert.equal(orderLineText(partial.state, "ar"), "منفَّذ جزئيًا");
  // «منفَّذ» never without evidence.
  assert.equal(orderLineState(journal("confirmed")).state, "uncertain");
  const unverified = { broker_id: "1", details: { verification: { status: "unverified" } } };
  assert.equal(orderLineState(journal("confirmed", { result: unverified })).state, "uncertain");
  const pending = { broker_id: "1", details: { verification: { status: "pending" } } };
  assert.equal(orderLineState(journal("confirmed", { result: pending })).state, "accepted");
  const limit = journal("confirmed", {
    request: { action: "buy_limit", symbol: "XAUUSD", volume: "0.10", price: "2300" },
    result: { broker_id: "9" },
  });
  assert.equal(orderLineState(limit).state, "accepted");
  assert.equal(orderLineState(journal("failed")).state, "rejected");
  const notSent = journal("failed", { send_state: "not_sent" });
  assert.equal(orderLineState(notSent).state, "blocked");
  assert.equal(orderLineState(journal("ambiguous")).state, "uncertain");
  assert.equal(orderLineText("uncertain", "ar"), "غير مؤكَّد");
  const attested = (outcome: string) =>
    journal("resolved", { result: { details: { resolution: { source: "owner", outcome } } } });
  const owner = orderLineState(attested("executed"));
  assert.equal(owner.state, "filled");
  assert.equal(owner.evidence, "owner");
  assert.equal(orderLineState(attested("not_executed")).state, "cancelled");
  assert.equal(orderLineState(attested("unknown")).state, "uncertain");
  assert.equal(orderLineText("accepted", "ar"), "مقبول لدى الوسيط");
});

// The MetaApi adapter's TradeResult (adapters/brokers/metaapi.py): the evidence lives in
// broker_id and details{order_id, position_id, deal_id, price, partial_execution}; the journal
// API adds verification_status beside it.
const metaapi = (details: Record<string, unknown>, broker_id: string | null = "71455") => ({
  operation_id: "op",
  status: "confirmed",
  broker_id,
  code: "TRADE_RETCODE_DONE",
  details: {
    partial_execution: false,
    numeric_code: 10009,
    order_id: "71455",
    position_id: "71455",
    deal_id: "88123",
    price: 2351.4,
    description: null,
    ...details,
  },
});

test("M1: the order line reads the executor's real fields, not top-level guesses", () => {
  const verified = orderLineState(
    journal("confirmed", { result: metaapi({}), verification_status: "verified" }),
  );
  assert.equal(verified.state, "filled");
  assert.equal(verified.ticket, "71455");
  assert.equal(verified.fill_price, "2351.4");
  // The broker's own partial flag wins, even when it reports no volume.
  const partial = orderLineState(
    journal("confirmed", {
      result: metaapi({ partial_execution: true, numeric_code: 10010 }),
      verification_status: "verified",
    }),
  );
  assert.equal(partial.state, "partial");
  assert.equal(partial.filled_volume, null);
  // Sent and acknowledged, the account state still being checked: accepted, no price.
  const checking = orderLineState(
    journal("confirmed", { result: metaapi({}), verification_status: "pending" }),
  );
  assert.equal(checking.state, "accepted");
  assert.equal(checking.fill_price, null);
  // A placed limit order rests at the broker: «مقبول لدى الوسيط», never filled, no fill price.
  const placed = orderLineState(
    journal("confirmed", {
      request: { action: "buy_limit", symbol: "XAUUSD", volume: "0.10", price: "2300" },
      result: metaapi({ position_id: null, deal_id: null, price: 2300 }),
    }),
  );
  assert.equal(placed.state, "accepted");
  assert.equal(placed.fill_price, null);
  // Only an order id and no broker_id is still evidence (the executor's reconciliation shape).
  const reconciled = orderLineState(
    journal("confirmed", { result: metaapi({ position_id: null, deal_id: null }, null) }),
  );
  assert.equal(reconciled.ticket, "71455");
  assert.equal(reconciled.state, "filled");
  // A pre-send block (risk limit) never reached the broker: not a broker rejection.
  const blocked = orderLineState(
    journal("failed", {
      send_state: "not_sent",
      result: { operation_id: "op", status: "failed", code: "risk_daily_loss_limit", details: {} },
    }),
  );
  assert.equal(blocked.state, "blocked");
  assert.equal(blocked.not_sent, true);
  const rejected = orderLineState(
    journal("failed", {
      send_state: "sent",
      result: { operation_id: "op", status: "failed", code: "TRADE_RETCODE_NO_MONEY", details: {} },
    }),
  );
  assert.equal(rejected.state, "rejected");
  assert.equal(rejected.not_sent, false);
});

test("M1: each action names itself; only entries and closes carry a volume", () => {
  assert.deepEqual(orderLineAction({ action: "buy", volume: "0.10" }, "ar"), {
    label: "شراء",
    volume: "0.10",
    direction: "up",
  });
  assert.equal(
    orderLineAction({ action: "close_position", volume: "0.05" }, "ar").label,
    "إغلاق صفقة",
  );
  const modify = orderLineAction({ action: "modify_position", volume: "0.10" }, "ar");
  assert.equal(modify.label, "تعديل صفقة");
  assert.equal(modify.volume, null);
  assert.equal(orderLineAction({ action: "cancel_order" }, "en").label, "Cancel pending order");
});

test("M1: the conversation's order line and sheet use the one shared helper", async () => {
  const { readFileSync } = await import("node:fs");
  const cards = readFileSync("apps/web/src/conversation/Cards.tsx", "utf8");
  assert.ok(cards.includes("orderLineState(row)"));
  // The evidence never comes from guessed top-level fields of the result.
  assert.ok(!/result\\??\.(order_id|position_id|deal_id|price|filled_volume)/.test(cards));
});

test("«حسم» opens the operation's own resolve card, and the order sheet offers «حسم العملية»", async () => {
  const { readFileSync } = await import("node:fs");
  const sheet = readFileSync("apps/web/src/conversation/sheets/AgentSheet.tsx", "utf8");
  assert.match(sheet, /openCard\(op\.resolve_card, go\)/);
  const conversation = readFileSync("apps/web/src/conversation/Conversation.tsx", "utf8");
  assert.match(conversation, /card\.facts\.operation\?\.operation_id === journalRow\.operation_id/);
  assert.match(conversation, /<OrderSheetBody\s+row=\{journalRow\}\s+onResolve=/);
});

test("the quota card follows Q22: no spend cap to raise, the provider's own quota", async () => {
  const { readFileSync } = await import("node:fs");
  const cards = readFileSync("apps/web/src/conversation/Cards.tsx", "utf8");
  assert.doesNotMatch(cards, /Edit the limit`|Raise the limit|usage limit/);
  assert.match(cards, /family === "quota"\s+\? t`View usage`/);
});

test("R1/R2: the executor's own rows: a never-sent order is Requested → Blocked; no «try again» on money", async () => {
  const { readFileSync } = await import("node:fs");
  const rows = JSON.parse(readFileSync("tests/fixtures/order-rows.json", "utf8"));
  const blocked = orderLineState(rows.not_sent);
  assert.deepEqual(blocked.steps, ["requested", "blocked"]);
  assert.equal(blocked.not_sent, true);
  assert.equal(orderLineText("blocked", "ar"), "أُوقف قبل الإرسال");
  const rejected = orderLineState(rows.rejected);
  assert.deepEqual(rejected.steps, ["requested", "sent", "rejected"]);
  // The sheet draws the shared steps and names the reason, never a generic retry.
  const cards = readFileSync("apps/web/src/conversation/Cards.tsx", "utf8");
  const sheet = cards.slice(cards.indexOf("export function OrderSheetBody"));
  assert.match(sheet, /line\.steps\.map/);
  assert.doesNotMatch(sheet.slice(0, sheet.indexOf("Technical details")), /userError\(/);
});

test("item 21: «Mandate details» opens the signed grant card of this chat", async () => {
  const { readFileSync } = await import("node:fs");
  const menu = readFileSync("apps/web/src/conversation/PermissionMenu.tsx", "utf8");
  assert.match(menu, /mandate\(agent, permission, true, threadId\)/);
  const sheet = readFileSync("apps/web/src/conversation/sheets/MandateSheet.tsx", "utf8");
  assert.match(sheet, /if \(card\) return <OwnerActionCard row=\{card\}/);
});

test("item 24: the call log has its own Arabic words", async () => {
  const { readFileSync } = await import("node:fs");
  const po = readFileSync("apps/web/src/i18n/locales/ar/messages.po", "utf8");
  const entry = (id: string, context?: string) => {
    const head = `${context ? `msgctxt "${context}"\n` : "\n"}msgid "${id}"\nmsgstr "`;
    const at = po.indexOf(head);
    assert.ok(at >= 0, `${context ?? ""} ${id}`);
    return po.slice(at + head.length, po.indexOf('"', at + head.length));
  };
  assert.equal(entry("Voice call", "call log"), "مكالمة صوتية");
  assert.equal(entry("Voice call"), "اتصال صوتي");
});
