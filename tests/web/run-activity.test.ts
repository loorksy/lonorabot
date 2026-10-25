import assert from "node:assert/strict";
import test from "node:test";
import type { Event, Run } from "../../apps/web/src/lib/api";
import { runActivity } from "../../apps/web/src/lib/run-activity";

const run = { id: "r", status: "running" } as Run;
const event = (kind: string, name = "") =>
  ({
    run_id: "r",
    kind,
    payload: { name, call_id: "a", text: kind === "run.delta" ? "hello" : "" },
  }) as Event;
test("activity follows actual model and tool transitions", () => {
  assert.equal(runActivity(run, []), "thinking");
  assert.equal(runActivity(run, [event("tool.started", "memory_search")]), "searching");
  assert.equal(runActivity(run, [event("tool.started", "chart_inspect")]), "analyzing");
  assert.equal(runActivity(run, [event("tool.started", "trade_execute")]), "executing");
  assert.equal(
    runActivity(run, [event("tool.started", "memory_search"), event("tool.completed")]),
    "thinking",
  );
  assert.equal(runActivity(run, [event("run.delta")]), "writing");
});
