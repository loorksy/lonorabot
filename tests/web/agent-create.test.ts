import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { AgentLiveState, AgentWatchSummary } from "../../packages/contracts/src/index";
import {
  agentStatusLine,
  liveAvatarState,
  watchCondition,
  watchUntil,
} from "../../packages/core/src/agent-status";

const now = new Date("2026-11-08T10:00:00Z");
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
    "Working",
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
