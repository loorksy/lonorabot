import assert from "node:assert/strict";
import test from "node:test";
import { parseRoute, recoveryPath } from "../../apps/web/src/shell/routes";

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

test("a broker outage opens the recovery page for its account", () => {
  assert.equal(recoveryPath("acct 1"), "/app/recovery?account=acct%201");
  assert.equal(recoveryPath(undefined), "/app/recovery");
});
