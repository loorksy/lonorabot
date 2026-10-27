import assert from "node:assert/strict";
import test from "node:test";
import type { Event, Payload, Run } from "@lonora/contracts";
import { projectRunEvents, turnActivity } from "../../packages/core/src/turn-activity";

const run: Run = {
  id: "run",
  thread_id: "thread",
  agent_id: "agent",
  parent_run_id: null,
  status: "running",
  trigger: "message",
  error_code: null,
  result: null,
  model_metadata: {},
  created_at: "2026-10-27T10:00:00.000Z",
  updated_at: "2026-10-27T10:00:00.100Z",
};
const event = (kind: string, cursor: number, payload: Payload = {}): Event => ({
  kind,
  cursor,
  payload,
  run_id: run.id,
  thread_id: run.thread_id,
  agent_id: run.agent_id,
  created_at: `2026-10-27T10:00:00.${String(cursor * 100).padStart(3, "0")}Z`,
});

test("queued and preparation are genuine states; thinking starts only on a model event", () => {
  assert.equal(turnActivity({ ...run, status: "queued" }, []).phase, "queued");
  assert.equal(turnActivity(run, []).phase, "preparing");
  assert.equal(turnActivity(run, [event("run.reply_started", 1)]).phase, "thinking");
  assert.equal(
    turnActivity(run, [event("run.delta", 2, { text: "Accepted prose." })]).phase,
    "writing",
  );
  assert.equal(turnActivity(run, [event("run.rich_partial", 2)]).phase, "writing");
  assert.equal(
    turnActivity(
      {
        ...run,
        stream: {
          turn_id: "turn",
          fence: 1,
          generation: 1,
          sequence: 1,
          text: "Durable preview.",
          phase: "streaming",
          truncated: false,
          message_id: null,
        },
      },
      [],
    ).phase,
    "writing",
  );
});

test("tool state is ordered by cursor and blank completion names cannot leave fake work running", () => {
  const started = event("tool.started", 2, { call_id: "call", name: "memory_search" });
  const finished = event("tool.completed", 3, { call_id: "call", name: "" });
  assert.equal(turnActivity(run, [started]).phase, "searching");
  const completed = turnActivity(run, [finished, event("run.reply_started", 1), started]);
  assert.equal(completed.phase, "thinking");
  assert.equal(completed.calls[0].status, "completed");
  assert.equal(completed.calls[0].name, "memory_search");
  assert.equal(
    turnActivity(run, [event("tool.started", 1, { call_id: "write", name: "memory_write" })])
      .avatar,
    "learning",
  );
  assert.equal(
    turnActivity(run, [event("tool.started", 1, { call_id: "peer", name: "peer_send" })]).avatar,
    "sending",
  );
});

test("terminal and input-waiting states override tools without inventing completion", () => {
  const events = [event("tool.started", 1, { call_id: "call", name: "market_read" })];
  assert.equal(turnActivity(run, events).phase, "analyzing");
  assert.equal(turnActivity({ ...run, status: "waiting_input" }, events).phase, "waiting_input");
  const cancelled = turnActivity({ ...run, status: "cancelled" }, events);
  assert.equal(cancelled.phase, "cancelled");
  assert.equal(cancelled.calls[0].status, "interrupted");
});

test("delayed GET and acknowledgement projections cannot regress a newer run", () => {
  const queued = { ...run, status: "queued" as const, updated_at: run.created_at };
  const completed = {
    ...run,
    status: "completed" as const,
    updated_at: "2026-10-27T10:00:00.500Z",
  };
  assert.equal(projectRunEvents([completed, queued], [], "thread")[0].status, "completed");
  const queuedEvent = event("run.queued", 1, { run: queued as unknown as Payload });
  assert.equal(projectRunEvents([completed], [queuedEvent], "thread")[0].status, "completed");
  const running = event("run.running", 2);
  assert.equal(projectRunEvents([queued], [running, queuedEvent], "thread")[0].status, "running");
  assert.deepEqual(projectRunEvents([], [queuedEvent], "other-thread"), []);
  assert.equal(projectRunEvents([], [queuedEvent], "thread")[0].status, "queued");
});

test("restored activity reflects actual work without a status fetch or replay", () => {
  const restored: Run = {
    ...run,
    model_metadata: {
      activity: {
        kind: "tool.started",
        name: "web_search",
        observed_at: "2026-10-27T10:00:00.400Z",
      },
    },
  };
  assert.equal(turnActivity(restored, []).phase, "searching");
  assert.equal(turnActivity(restored, [event("run.reply_started", 1)]).phase, "searching");
  assert.equal(
    turnActivity(restored, [event("run.delta", 5, { text: "The result." })]).phase,
    "writing",
  );
  assert.equal(turnActivity({ ...restored, status: "completed" }, []).phase, "completed");
  assert.equal(
    turnActivity(run, [event("tool.started", 2, { call_id: "exec", name: "workspace_execute" })])
      .phase,
    "executing",
  );
  assert.equal(
    turnActivity(run, [event("tool.started", 2, { call_id: "read", name: "web_fetch" })]).phase,
    "reading",
  );
  assert.equal(
    turnActivity(run, [event("tool.started", 2, { call_id: "read", name: "trade_record_read" })])
      .phase,
    "reading",
  );
});
