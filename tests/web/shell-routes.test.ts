import assert from "node:assert/strict";
import test from "node:test";
import { parseRoute, recoveryPath, sectionOf } from "../../apps/web/src/shell/routes";

test("inherited object names are not route aliases", () => {
  for (const name of ["constructor", "toString", "hasOwnProperty", "__proto__"])
    assert.deepEqual(parseRoute(`/app/${name}`), { kind: "chat", agentId: name });
  assert.deepEqual(parseRoute("/app/board"), { kind: "alias", to: "/app/tasks" });
});

test("the agent, identity, trades and group pages carry their item", () => {
  assert.deepEqual(parseRoute("/app/agent/a1"), { kind: "page", page: "agent", item: "a1" });
  assert.deepEqual(parseRoute("/app/identity/a1"), { kind: "page", page: "identity", item: "a1" });
  assert.deepEqual(parseRoute("/app/trades/a1"), { kind: "page", page: "trades", item: "a1" });
  assert.deepEqual(parseRoute("/app/group/g1"), { kind: "page", page: "group", item: "g1" });
  assert.deepEqual(parseRoute("/app/g/g1"), { kind: "group", groupId: "g1" });
  assert.deepEqual(parseRoute("/app/recovery"), { kind: "page", page: "recovery" });
  for (const bare of ["/app/agent", "/app/identity", "/app/trades", "/app/group"])
    assert.deepEqual(parseRoute(bare), { kind: "not-found" });
  assert.deepEqual(parseRoute("/app/recovery/x"), { kind: "not-found" });
});

test("the rail keeps Settings on workspace files and recovery, Tasks on a new schedule", () => {
  assert.equal(sectionOf(parseRoute("/app/artifacts"), ""), "settings");
  assert.equal(sectionOf(parseRoute("/app/artifacts"), "?agent=a1"), "chats");
  assert.equal(sectionOf(parseRoute("/app/artifacts/x"), ""), "chats");
  assert.equal(sectionOf(parseRoute("/app/recovery")), "settings");
  assert.equal(sectionOf(parseRoute("/app/new-schedule")), "tasks");
  assert.equal(sectionOf(parseRoute("/app/new-task")), "tasks");
});

test("a broker outage opens the recovery page for its account", () => {
  assert.equal(recoveryPath("acct 1"), "/app/recovery?account=acct%201");
  assert.equal(recoveryPath(undefined), "/app/recovery");
});

test("domain pages: the task and skill pages take their id in the path, the rest query params", () => {
  assert.deepEqual(parseRoute("/app/tasks/t1"), { kind: "page", page: "task", item: "t1" });
  assert.deepEqual(parseRoute("/app/skills/k1"), { kind: "page", page: "skill", item: "k1" });
  assert.deepEqual(parseRoute("/app/tasks"), { kind: "root", root: "tasks" });
  assert.deepEqual(parseRoute("/app/goals"), { kind: "page", page: "goals" });
  assert.deepEqual(parseRoute("/app/activity"), { kind: "page", page: "activity" });
  assert.deepEqual(parseRoute("/app/task"), { kind: "not-found" });
  assert.deepEqual(parseRoute("/app/goals/x"), { kind: "not-found" });
  assert.deepEqual(parseRoute("/app/tasks/t1/x"), { kind: "not-found" });
});

test("calls: «المكالمة» is one page, «مكالمة واردة» takes its call id in the path", () => {
  assert.deepEqual(parseRoute("/app/call"), { kind: "page", page: "call" });
  assert.deepEqual(parseRoute("/app/call/x"), { kind: "not-found" });
  assert.deepEqual(parseRoute("/app/incoming/c1"), { kind: "page", page: "incoming", item: "c1" });
  assert.deepEqual(parseRoute("/app/incoming/c1/x"), { kind: "not-found" });
});

test("settings: «النماذج» is an inner settings page", () => {
  const route = parseRoute("/app/models");
  assert.deepEqual(route, { kind: "page", page: "models" });
  assert.equal(sectionOf(route), "settings");
  assert.deepEqual(parseRoute("/app/models/x"), { kind: "not-found" });
});
