import assert from "node:assert/strict";
import test from "node:test";
import type { Event, Run } from "../../apps/web/src/lib/api";
import { runActivity } from "../../apps/web/src/lib/run-activity";

const run = { id: "r", status: "running" } as Run;
// The server reports each tool's registry toolset and effect with tool.started.
const tools: Record<string, { toolset: string; effect: string }> = {
  web_search: { toolset: "research", effect: "read" },
  chart_inspect: { toolset: "charts", effect: "read" },
  trade_execute: { toolset: "trading", effect: "financial" },
};
const event = (kind: string, name = "") =>
  ({
    run_id: "r",
    kind,
    payload: { name, call_id: "a", text: kind === "run.delta" ? "hello" : "", ...tools[name] },
  }) as Event;
test("activity follows actual model and tool transitions", () => {
  assert.equal(runActivity(run, []), "thinking");
  assert.equal(runActivity(run, [event("tool.started", "web_search")]), "searching");
  assert.equal(runActivity(run, [event("tool.started", "chart_inspect")]), "analyzing");
  assert.equal(runActivity(run, [event("tool.started", "trade_execute")]), "executing");
  assert.equal(
    runActivity(run, [event("tool.started", "web_search"), event("tool.completed")]),
    "thinking",
  );
  assert.equal(runActivity(run, [event("run.delta")]), "writing");
});
