import assert from "node:assert/strict";
import test from "node:test";
import { parseRoute } from "../../apps/web/src/shell/routes";

test("inherited object names are not route aliases", () => {
  for (const name of ["constructor", "toString", "hasOwnProperty", "__proto__"])
    assert.deepEqual(parseRoute(`/app/${name}`), { kind: "chat", agentId: name });
  assert.deepEqual(parseRoute("/app/board"), { kind: "alias", to: "/app/tasks" });
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
