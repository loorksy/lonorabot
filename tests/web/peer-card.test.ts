// One peer card on Web and Mobile (P1-05): which messages draw an exchange between two
// agents, who asked whom, its status and its text all come from `@lonora/core`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import type { Resource } from "@lonora/contracts";
import { peerCard, peersByMessage } from "../../packages/core/src/peer-outcome";

const exchange = (extra: Record<string, unknown> = {}): Resource =>
  ({
    id: "peer-1",
    agent_id: "trader",
    thread_id: "trader-thread",
    payload: {
      run_id: "child-run",
      task: "Check gold",
      source_agent_id: "analyst",
      source_agent_name: "Analyst",
      source_thread_id: "analyst-thread",
      target_agent_id: "trader",
      target_agent_name: "Trader",
      target_thread_id: "trader-thread",
      source_message_id: "request-in-analyst",
      target_message_id: "request-in-trader",
      status: "queued",
      ...extra,
    },
    version: 1,
    created_at: "2026-11-26T10:00:00Z",
    updated_at: "2026-11-26T10:00:00Z",
  }) as Resource;

const asker = { id: "analyst", name: "Analyst", thread: "analyst-thread" };
const asked = { id: "trader", name: "Trader", thread: "trader-thread" };
const outcome = (status: string, text: string) =>
  `<peer_outcome run_id='child-run' status='${status}'>\n${text}\n</peer_outcome>`;

test("the request and every returned result in both conversations draw the exchange", () => {
  const row = exchange({
    source_outcome_message_id: "result-2",
    source_outcome_message_ids: ["result-1", "result-2", 7],
    target_outcome_message_id: "answer-in-trader",
  });
  const drawn = peersByMessage([row, exchange({ source_message_id: null })]);
  assert.deepEqual(
    [...drawn.keys()].sort(),
    ["answer-in-trader", "request-in-analyst", "request-in-trader", "result-1", "result-2"].sort(),
  );
  assert.equal(drawn.get("result-1"), row);
});

test("a request reads asker to asked; a returned result reads the other way", () => {
  const row = exchange();
  assert.deepEqual(peerCard({ id: "request-in-analyst", content: "Check gold" }, row), {
    kind: "request",
    from: asker,
    to: asked,
    status: "queued",
    body: "Check gold",
  });
  assert.deepEqual(
    peerCard({ id: "result-1", content: outcome("completed", "Gold held 2410.") }, row),
    { kind: "outcome", from: asked, to: asker, status: "completed", body: "Gold held 2410." },
  );
  // A row written before names were stored still draws, with no name to show.
  const bare = exchange({ source_agent_name: undefined, source_agent_id: undefined });
  assert.deepEqual(peerCard({ id: "request-in-trader", content: "Check gold" }, bare).from, {
    id: "",
    name: "",
    thread: "analyst-thread",
  });
});

test("the status is the result's own, then the live run's, then the stored row's", () => {
  const status = (content: string, run?: string, stored = "queued") =>
    peerCard({ id: "request-in-trader", content }, exchange({ status: stored }), run).status;
  assert.equal(status(outcome("failed", "model_not_configured"), "completed"), "failed");
  assert.equal(status("Check gold", "running"), "working");
  assert.equal(status("Check gold", "leased"), "working");
  assert.equal(status("Check gold", undefined, "limited"), "limited");
  assert.equal(status("Check gold", undefined, "cancelled"), "cancelled");
  assert.equal(status("Check gold", undefined, "completed"), "completed");
  // Anything not yet started or not named above waits in the queue.
  assert.equal(status("Check gold", "waiting_input"), "queued");
  assert.equal(status("Check gold"), "queued");
});

test("a bare cancellation shows only its status; a cancellation with words keeps them", () => {
  const row = exchange();
  assert.equal(
    peerCard({ id: "result-1", content: outcome("cancelled", "cancelled") }, row).body,
    null,
  );
  assert.equal(
    peerCard({ id: "result-1", content: outcome("cancelled", "Stopped by the owner") }, row).body,
    "Stopped by the owner",
  );
});

test("Web draws the card from the core helpers", () => {
  const read = (path: string) => readFileSync(path, "utf8");
  assert.match(read("apps/web/src/conversation/Cards.tsx"), /\bpeerCard\(/);
  assert.match(read("apps/web/src/conversation/Conversation.tsx"), /\bpeersByMessage\(/);
  // The rules live in core only: the client never reads the exchange's sides itself.
  assert.doesNotMatch(
    read("apps/web/src/conversation/Cards.tsx"),
    /source_agent_id|target_agent_id|source_message_id/,
  );
});
