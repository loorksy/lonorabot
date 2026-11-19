import assert from "node:assert/strict";
import test from "node:test";
import type { Agent, OwnerAction, SupervisionView } from "../../packages/contracts/src/index";
import { ownerActionCard } from "../../packages/core/src/owner-actions";
import {
  supervisionError,
  supervisionLabels,
  supervisionRows,
  unsupervisedAgents,
} from "../../packages/core/src/supervision";

const isolated = (value: string) => `⁨${value}⁩`;
const names = { supervisor_name: "Watcher", supervised_names: ["Gold agent", "Silver agent"] };
const proposal: OwnerAction = {
  id: "card",
  kind: "supervise",
  status: "pending",
  status_reason: null,
  source: "agent",
  agent_id: "watcher",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 4,
  facts: {
    several_accounts: false,
    supervision: { ...names, active: false },
  },
  requires_passkey: false,
  result: {},
  expires_at: "2026-11-09T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T10:00:00Z",
  updated_at: "2026-11-08T10:00:00Z",
};
const created: OwnerAction = {
  ...proposal,
  id: "undo",
  kind: "supervision_created",
  source: "system",
  facts: { ...proposal.facts, supervision: { ...names, active: true } },
};

test("a supervision card names who supervises whom and promises no money authority", () => {
  for (const locale of ["en", "ar"] as const) {
    const spec = ownerActionCard(proposal, locale);
    const text = supervisionLabels[locale];
    assert.equal(spec.lines.length, 2);
    assert.ok(spec.lines[0]?.includes(isolated("Watcher")), spec.lines[0]);
    assert.ok(spec.lines[1]?.includes(isolated("Silver agent")), spec.lines[1]);
    // Each line starts with a word in the owner's language, never with a Latin name.
    for (const line of spec.lines) assert.ok(!line.startsWith("⁨"), line);
    assert.equal(spec.passkey, false);
    assert.deepEqual(
      spec.buttons.map((button) => button.decision),
      ["confirm", "cancel"],
    );
    assert.ok(spec.hint && spec.hint.length > 40);
    assert.ok(text.stop.length > 0);
  }
  assert.match(ownerActionCard(proposal, "en").hint ?? "", /never trades/);
  assert.match(ownerActionCard(proposal, "ar").hint ?? "", /لا يتداول/);
});

test("the Undo card stops supervision, and an ended one can only be dismissed", () => {
  const spec = ownerActionCard(created, "en");
  assert.equal(spec.title, "Supervision set");
  assert.deepEqual(
    spec.buttons.map((button) => button.label),
    ["Undo", "Keep it"],
  );
  const ended = ownerActionCard(
    {
      ...created,
      facts: { ...created.facts, supervision: { ...names, active: false } },
    },
    "ar",
  );
  assert.deepEqual(
    ended.buttons.map((button) => button.decision),
    ["cancel"],
  );
  const undone = ownerActionCard({ ...created, status: "confirmed", result: { revoked: 1 } }, "en");
  assert.equal(undone.outcome, "Undone: supervision stopped.");
  const set = ownerActionCard({ ...proposal, status: "confirmed" }, "ar");
  assert.equal(set.outcome, "تم تعيين الإشراف.");
  const stale = ownerActionCard(
    { ...proposal, status: "expired", status_reason: "supervision_already_set" },
    "en",
  );
  assert.equal(stale.outcome, "This supervision is already set. Nothing changed.");
});

test("a Restore card sets stopped supervision again, until it is set elsewhere", () => {
  const stopped: OwnerAction = {
    ...created,
    id: "stopped",
    kind: "supervision_stopped",
    facts: { ...created.facts, supervision: { ...names, active: true } },
  };
  const spec = ownerActionCard(stopped, "en");
  assert.equal(spec.title, "Supervision stopped");
  assert.deepEqual(
    spec.buttons.map((button) => [button.label, button.decision]),
    [
      ["Restore", "confirm"],
      ["Keep it", "cancel"],
    ],
  );
  const arabic = ownerActionCard(stopped, "ar");
  assert.equal(arabic.title, "توقف الإشراف");
  for (const line of arabic.lines) assert.ok(!line.startsWith("⁨"), line);
  const setElsewhere = ownerActionCard(
    { ...stopped, facts: { ...stopped.facts, supervision: { ...names, active: false } } },
    "en",
  );
  assert.deepEqual(
    setElsewhere.buttons.map((button) => button.decision),
    ["cancel"],
  );
  assert.equal(
    ownerActionCard({ ...stopped, status: "confirmed", result: { restored: 1 } }, "en").outcome,
    "Restored: supervision set again.",
  );
});

test("a pause card names the supervisor, the agent and the item, with one-tap Resume", () => {
  const held = {
    supervisor_name: "Lonora",
    supervised_names: ["Gold agent"],
    active: true,
    target: "routine" as const,
    target_label: "Review XAUUSD before London",
    from_owner_message: false,
    owner_holds: false,
  };
  const pause: OwnerAction = {
    ...created,
    id: "pause",
    kind: "supervision_paused",
    agent_id: "gold",
    facts: { several_accounts: false, supervision: held },
  };
  for (const locale of ["en", "ar"] as const) {
    const spec = ownerActionCard(pause, locale);
    assert.equal(spec.lines.length, 3);
    assert.ok(spec.lines[0]?.includes(isolated("Lonora")), spec.lines[0]);
    assert.ok(spec.lines[1]?.includes(isolated("Gold agent")), spec.lines[1]);
    assert.ok(spec.lines[2]?.includes(isolated("Review XAUUSD before London")), spec.lines[2]);
    for (const line of spec.lines) assert.ok(!line.startsWith("⁨"), line);
    assert.deepEqual(
      spec.buttons.map((button) => [button.decision, button.primary]),
      [
        ["confirm", true],
        ["cancel", false],
      ],
    );
  }
  const english = ownerActionCard(pause, "en");
  assert.equal(english.title, "Paused by a supervisor");
  assert.equal(english.lines[2], `What: Routine · ${isolated("Review XAUUSD before London")}`);
  assert.equal(ownerActionCard(pause, "ar").lines[2]?.startsWith("ما أُوقف: مهمة مجدولة"), true);
  const ownerHolds = ownerActionCard(
    {
      ...pause,
      facts: {
        ...pause.facts,
        supervision: { ...held, owner_holds: true, from_owner_message: true },
      },
    },
    "en",
  );
  assert.equal(ownerHolds.hint, "This pause is yours: only you resume it.");
  assert.ok(ownerHolds.lines[0]?.endsWith("from your message"), ownerHolds.lines[0]);
  const ended = ownerActionCard(
    {
      ...pause,
      facts: { ...pause.facts, supervision: { ...held, active: false } },
    },
    "ar",
  );
  assert.deepEqual(
    ended.buttons.map((button) => button.decision),
    ["cancel"],
  );
  assert.equal(ownerActionCard({ ...pause, status: "confirmed" }, "en").outcome, "Resumed.");
  assert.equal(ownerActionCard({ ...pause, status: "cancelled" }, "ar").outcome, "بقي موقوفًا.");
  assert.equal(
    ownerActionCard({ ...pause, status: "expired", status_reason: "supervision_pause_ended" }, "en")
      .outcome,
    "This pause already ended. Nothing changed.",
  );
});

test("profile rows name the other agent and where each grant came from", () => {
  const view: SupervisionView = {
    agent_id: "lonora",
    supervises: [
      {
        id: "g1",
        supervisor: { id: "lonora", name: "Lonora" },
        supervised: { id: "gold", name: "Gold agent" },
        created_via: "default",
        created_at: "2026-11-08T10:00:00Z",
        revoked_at: null,
        revoked_via: null,
      },
    ],
    supervised_by: [],
  };
  const rows = supervisionRows(view, "ar");
  assert.deepEqual(rows.supervises, [
    { grantId: "g1", agentId: "gold", name: isolated("Gold agent"), source: "افتراضيًا" },
  ]);
  assert.equal(supervisionRows(view, "en").supervises[0]?.source, "by default");
  const agents = [
    { id: "lonora", name: "Lonora" },
    { id: "gold", name: "Gold agent" },
    { id: "news", name: "News agent" },
  ] as Agent[];
  assert.deepEqual(
    unsupervisedAgents(view, agents).map((agent) => agent.id),
    ["news"],
  );
  assert.equal(
    supervisionError("supervision_self_target", "en"),
    "An agent cannot supervise itself.",
  );
  assert.equal(supervisionError("unknown_code", "ar"), null);
  for (const key of Object.keys(supervisionLabels.en)) assert.ok(key in supervisionLabels.ar, key);
});
