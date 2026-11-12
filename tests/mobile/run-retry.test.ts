// A failed reply's Retry (Q22), shared by Web and mobile through packages/core: only the newest
// failure of the conversation, never one already retried, never a failure outside the provider
// families (it may have touched the executor), and not before the provider's Retry-After.
import assert from "node:assert/strict";
import test from "node:test";
import type { Run } from "../../packages/contracts/src";
import { retryableFailure, runFailure } from "../../packages/core/src/run-state";

const run = (id: string, fields: Partial<Run> = {}): Run =>
  ({
    id,
    thread_id: "t",
    agent_id: "a",
    parent_run_id: null,
    status: "failed",
    trigger: "user",
    input_seq: 1,
    model_metadata: {},
    result: null,
    error_code: "provider_unavailable",
    created_at: `2026-11-12T06:0${id}:00Z`,
    updated_at: `2026-11-12T06:0${id}:00Z`,
    ...fields,
  }) as Run;

test("the failure family comes from the server, else from the error code", () => {
  assert.deepEqual(runFailure(run("1", { failure: { family: "rate", retry_after_seconds: 12 } })), {
    family: "rate",
    retryAfter: 12,
  });
  assert.equal(runFailure(run("1", { error_code: "provider_quota_exceeded" })).family, "quota");
  assert.equal(runFailure(run("1", { error_code: "rate_limited" })).retryAfter, 30);
  assert.equal(runFailure(run("1", { error_code: "model_timeout" })).family, "timeout");
  assert.equal(runFailure(run("1", { error_code: "execution_uncertain" })).family, "other");
});

test("only the newest provider failure, not yet retried, once its wait is over", () => {
  const now = Date.parse("2026-11-12T06:10:00Z");
  const old = run("1"),
    newer = run("2");
  assert.equal(retryableFailure([old, newer], now)?.run.id, "2");
  const retried = run("3", { status: "running", model_metadata: { retry_of: "2" } });
  assert.equal(retryableFailure([old, newer, retried], now), null);
  assert.equal(retryableFailure([run("4", { error_code: "execution_uncertain" })], now), null);
  const waiting = run("5", { failure: { family: "rate", retry_after_seconds: 600 } });
  assert.equal(retryableFailure([waiting], now)?.ready, false);
  assert.equal(retryableFailure([waiting], now + 600_000)?.ready, true);
  assert.equal(retryableFailure([run("6", { status: "succeeded" })], now), null);
});

test("only the owner's replies are retried: never a routine's, a peer's or a subagent's run", () => {
  const now = Date.parse("2026-11-12T06:10:00Z");
  assert.equal(retryableFailure([run("1", { trigger: "routine" })], now), null);
  assert.equal(retryableFailure([run("1", { parent_run_id: "p" })], now), null);
  assert.equal(retryableFailure([run("1", { trigger: "group" })], now)?.run.id, "1");
  // A newer background run does not hide the owner's failed reply.
  const reply = run("1");
  const routine = run("2", { trigger: "routine", status: "succeeded" });
  assert.equal(retryableFailure([reply, routine], now)?.run.id, "1");
});
