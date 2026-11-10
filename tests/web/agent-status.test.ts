import assert from "node:assert/strict";
import test from "node:test";
import type { AgentLiveState, Journal } from "../../packages/contracts/src/index";
import { agentStatusLine, uncertainLine } from "../../packages/core/src/agent-status";
import { orderLineState, orderLineText } from "../../packages/core/src/order-line";

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
    current_work: { kind: "broker" as const, text: "شراء 0.10 XAUUSD", until: null, run_id: "r" },
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
    current_work: { kind: "waiting_owner", text: "قرار مطلوب", until: null, run_id: null },
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
  assert.equal(orderLineState(notSent).state, "cancelled");
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
