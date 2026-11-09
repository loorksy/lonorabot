import assert from "node:assert/strict";
import test from "node:test";
import { parseRoute } from "../../apps/web/src/shell/routes";

test("inherited object names are not route aliases", () => {
  for (const name of ["constructor", "toString", "hasOwnProperty", "__proto__"])
    assert.deepEqual(parseRoute(`/app/${name}`), { kind: "chat", agentId: name });
  assert.deepEqual(parseRoute("/app/board"), { kind: "alias", to: "/app/tasks" });
});
