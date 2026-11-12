import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type {
  AgentLiveState,
  AgentWatchSummary,
  OwnerAction,
} from "../../packages/contracts/src/index";
import {
  agentStatusLine,
  liveAvatarState,
  watchCondition,
  watchUntil,
} from "../../packages/core/src/agent-status";
import { ownerActionCard } from "../../packages/core/src/owner-actions";

const now = new Date("2026-11-08T10:00:00Z");
const created: OwnerAction = {
  id: "card",
  kind: "agent_created",
  status: "pending",
  status_reason: null,
  source: "system",
  agent_id: "lonora",
  thread_id: "thread",
  run_id: "run",
  timeline_seq: 3,
  facts: {
    several_accounts: true,
    account: { id: "acct", label: "Broker · 1234 · Live", provider: "metaapi" },
    agent: {
      exists: true,
      name: "Gold agent",
      template: "trading",
      symbol: "XAUUSD",
      level: "supervised",
      paused: false,
      report_to: [],
      model: null,
    },
    undo: "delete",
  },
  requires_passkey: false,
  result: { agent_name: "Gold agent" },
  expires_at: "2026-11-15T10:00:00Z",
  decided_at: null,
  decided_via: null,
  created_at: "2026-11-08T09:30:00Z",
  updated_at: "2026-11-08T09:30:00Z",
};
const proposal: OwnerAction = {
  ...created,
  id: "proposal",
  kind: "create_agent",
  source: "agent",
  facts: {
    several_accounts: false,
    agent: {
      exists: false,
      name: "News agent",
      template: "research",
      symbol: null,
      level: "analysis",
      paused: false,
      report_to: ["Gold agent", "Silver agent"],
      model: null,
    },
  },
};
const watch: AgentWatchSummary = {
  id: "watch",
  kind: "price",
  account_id: "acct",
  symbol: "XAUUSD",
  condition: "above",
  level: "2100",
  indicator: null,
  timeframe: null,
  metric: null,
  expires_at: "2026-11-08T17:00:00Z",
  lifecycle: "pending",
};
const monitoring: AgentLiveState = {
  agent_id: "gold",
  observed_at: now.toISOString(),
  state: "waiting",
  phase: "monitoring",
  reason_code: "market_watch",
  pending_approval_count: 0,
  watch_count: 3,
  watches: [watch],
  tasks: [],
  health: [],
};

test("the result card names the agent, its pair on the account and Ask me, with Undo", () => {
  const en = ownerActionCard(created, "en", now);
  assert.equal(en.title, "Agent created");
  assert.deepEqual(en.lines, [
    "Trading agent · ⁨Gold agent⁩",
    "Focus pair: ⁨XAUUSD⁩ on ⁨Broker · 1234 · Live⁩",
    "Trading level: Ask me",
  ]);
  assert.match(en.hint ?? "", /every trade waits for your tap/);
  assert.match(en.hint ?? "", /Undo removes it/);
  assert.deepEqual(
    en.buttons.map((button) => [button.label, button.decision]),
    [
      ["Undo", "confirm"],
      ["Keep it", "cancel"],
    ],
  );
  const ar = ownerActionCard(created, "ar", now);
  assert.equal(ar.title, "أُنشئ وكيل");
  assert.equal(ar.lines[0], "وكيل تداول · ⁨Gold agent⁩");
  assert.equal(ar.lines[1], "زوج التركيز: ⁨XAUUSD⁩ على ⁨Broker · 1234 · Live⁩");
  assert.equal(ar.lines[2], "مستوى التداول: يسألني أولًا");
  assert.deepEqual(
    ar.buttons.map((button) => button.label),
    ["تراجع", "إبقاؤه"],
  );
});

test("Undo says what it does: remove an untouched agent, pause one that started", () => {
  const started = { ...created, facts: { ...created.facts, undo: "pause" as const } };
  assert.match(ownerActionCard(started, "en", now).hint ?? "", /Undo pauses it/);
  assert.match(ownerActionCard(started, "ar", now).hint ?? "", /يوقفه مؤقتًا/);
  const removed = {
    ...created,
    status: "confirmed" as const,
    result: { undo: "deleted" as const, agent_name: "Gold agent" },
  };
  assert.equal(ownerActionCard(removed, "en", now).outcome, "Undone: the agent was removed.");
  assert.deepEqual(ownerActionCard(removed, "en", now).buttons, []);
  const paused = { ...removed, result: { undo: "paused" as const } };
  assert.equal(
    ownerActionCard(paused, "ar", now).outcome,
    "تم التراجع: أُوقف الوكيل مؤقتًا، وبقي ما أنجزه.",
  );
  const kept = { ...created, status: "cancelled" as const };
  assert.equal(ownerActionCard(kept, "en", now).outcome, "Kept.");
  const gone = {
    ...created,
    facts: { several_accounts: false, agent: { exists: false, name: "Gold agent" } },
  };
  const spec = ownerActionCard(gone, "en", now);
  assert.deepEqual(
    spec.buttons.map((button) => button.decision),
    ["cancel"],
  );
});

test("the Undo card's authority sentence follows the live level, a signed grant included", () => {
  const agent = created.facts.agent;
  assert.ok(agent);
  const signed = {
    ...created,
    facts: { ...created.facts, agent: { ...agent, level: "autonomous" as const } },
  };
  const en = ownerActionCard(signed, "en", now);
  assert.equal(en.lines[2], "Trading level: On its own (signed)");
  assert.match(en.hint ?? "", /^It trades on its own only inside the grant you signed\./);
  assert.doesNotMatch(en.hint ?? "", /No money authority|waits for your tap/);
  const ar = ownerActionCard(signed, "ar", now);
  assert.equal(ar.lines[2], "مستوى التداول: مستقل ضمن تفويضي الموقّع");
  assert.match(ar.hint ?? "", /^يتداول وحده فقط ضمن التفويض الذي وقّعته\./);
  assert.doesNotMatch(ar.hint ?? "", /لا يملك صلاحية مالية|تنتظر لمستك/);
  const research = {
    ...created,
    facts: {
      ...created.facts,
      agent: { ...agent, template: "research" as const, level: "analysis" as const },
    },
  };
  assert.match(ownerActionCard(research, "en", now).hint ?? "", /^It does not trade\./);
  assert.match(ownerActionCard(research, "ar", now).hint ?? "", /^لا يتداول\./);
});

test("both cards show the stored task word for word, isolated and labelled", () => {
  const task = "Follow economic news\n and report  important items.";
  const proposed = proposal.facts.agent;
  const result = created.facts.agent;
  assert.ok(proposed && result);
  const asked = {
    ...proposal,
    facts: { ...proposal.facts, agent: { ...proposed, responsibility: task } },
  };
  const en = ownerActionCard(asked, "en", now);
  assert.equal(en.lines.at(-1), "Its task: ⁨Follow economic news and report important items.⁩");
  const ar = ownerActionCard(asked, "ar", now);
  assert.equal(ar.lines.at(-1), "مهمته: ⁨Follow economic news and report important items.⁩");
  const quoted = {
    ...created,
    facts: { ...created.facts, agent: { ...result, responsibility: "تابع الذهب وأبلغني" } },
  };
  assert.equal(ownerActionCard(quoted, "ar", now).lines.at(-1), "مهمته: ⁨تابع الذهب وأبلغني⁩");
  assert.equal(ownerActionCard(created, "en", now).lines.length, 3);
});

test("a creation card without an owner message asks before anything exists", () => {
  const en = ownerActionCard(proposal, "en", now);
  assert.equal(en.title, "Create an agent?");
  assert.deepEqual(en.lines, [
    "Research agent · ⁨News agent⁩",
    "Trading level: No trading",
    "Reports to: ⁨Gold agent⁩, ⁨Silver agent⁩",
  ]);
  assert.match(en.hint ?? "", /no money authority/);
  assert.deepEqual(
    en.buttons.map((button) => [button.label, button.decision, button.primary]),
    [
      ["Create agent", "confirm", true],
      ["Not now", "cancel", false],
    ],
  );
  const ar = ownerActionCard(proposal, "ar", now);
  assert.equal(ar.lines[2], "يبلغ: ⁨Gold agent⁩، ⁨Silver agent⁩");
  const done = { ...proposal, status: "confirmed" as const };
  assert.equal(ownerActionCard(done, "en", now).outcome, "Agent created.");
  const answered = {
    ...proposal,
    status: "superseded" as const,
    status_reason: "agent_already_created",
  };
  assert.equal(
    ownerActionCard(answered, "en", now).outcome,
    "This agent was already created. Nothing changed.",
  );
  assert.equal(
    ownerActionCard(answered, "ar", now).outcome,
    "أُنشئ هذا الوكيل مسبقًا. لم يتغير شيء.",
  );
  assert.deepEqual(ownerActionCard(answered, "en", now).buttons, []);
});

test("the status line says what it monitors and until when, in both languages", () => {
  assert.equal(
    agentStatusLine(monitoring, "en", now),
    `Monitoring ⁨XAUUSD⁩ until ${watchUntil(watch, "en", now).replace("until ", "")} · ⁨2⁩ more`,
  );
  assert.match(agentStatusLine(monitoring, "ar", now), /^يراقب ⁨XAUUSD⁩ حتى ⁨.+⁩ · ⁨2⁩ أخرى$/);
  const one = { ...monitoring, watch_count: 1, watches: [{ ...watch, expires_at: null }] };
  assert.equal(agentStatusLine(one, "en", now), "Monitoring ⁨XAUUSD⁩");
  assert.equal(
    agentStatusLine({ ...monitoring, phase: "thinking", state: "working" }, "en"),
    "Analysing",
  );
  assert.equal(
    agentStatusLine({ ...monitoring, phase: "paused", state: "paused" }, "ar"),
    "متوقف مؤقتًا",
  );
  assert.equal(
    agentStatusLine({ ...monitoring, phase: "action_required", state: "action_required" }, "ar"),
    "بانتظار قرارك",
  );
});

test("each watch shows its condition and expiry, never its prompt", () => {
  assert.equal(watchCondition(watch, "en"), "⁨XAUUSD⁩ above ⁨2100⁩");
  assert.equal(watchCondition(watch, "ar"), "⁨XAUUSD⁩ فوق ⁨2100⁩");
  const rsi = {
    ...watch,
    kind: "indicator" as const,
    indicator: "rsi",
    timeframe: "1h",
    condition: "cross_above" as const,
    level: "70",
  };
  assert.equal(watchCondition(rsi, "en"), "⁨RSI⁩ ⁨1h⁩ ⁨XAUUSD⁩ crosses above ⁨70⁩");
  const account = {
    ...watch,
    kind: "account" as const,
    symbol: null,
    metric: "equity",
    condition: "below" as const,
    level: "9000",
  };
  assert.equal(watchCondition(account, "en"), "Account equity below ⁨9000⁩");
  assert.equal(watchUntil({ ...watch, expires_at: null }, "ar"), "حتى الإلغاء");
});

test("the avatar follows the server phase between runs", () => {
  assert.equal(liveAvatarState(monitoring), "inspecting");
  assert.equal(liveAvatarState({ ...monitoring, state: "paused" }), "sleeping");
  assert.equal(liveAvatarState({ ...monitoring, state: "action_required" }), "warning");
  assert.equal(liveAvatarState({ ...monitoring, phase: "idle", state: "idle" }), "waiting");
  assert.equal(liveAvatarState(null), "waiting");
});

test("web and mobile render the same status line, watch list and avatar", () => {
  // The surfaces the web actually mounts: the agent sheet's status line and the watches sheet.
  const web = [
    "apps/web/src/conversation/sheets/AgentSheet.tsx",
    "apps/web/src/conversation/sheets/WatchesSheet.tsx",
  ]
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");
  const mobile = readFileSync("apps/mobile/components/agent-live-status.tsx", "utf8");
  for (const name of ["agentStatusLine", "watchCondition", "watchUntil", "/control"]) {
    assert.ok(web.includes(name), `the web sheets use ${name}`);
    assert.ok(mobile.includes(name), `mobile uses ${name}`);
  }
  // …and the chat really opens them (the header's capsule and the chat menu).
  for (const path of ["apps/web/src/shell/ChatMenu.tsx", "apps/web/src/shell/ChatHeader.tsx"])
    assert.ok(readFileSync(path, "utf8").includes("useAgentSheet"), path);
  for (const path of ["apps/web/src/shell/Shell.tsx", "apps/mobile/app/thread.tsx"])
    assert.ok(readFileSync(path, "utf8").includes("liveAvatarState"), path);
});
