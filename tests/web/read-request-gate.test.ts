import assert from "node:assert/strict";
import test from "node:test";
import { ReadRequestGate } from "../../packages/core/src/read-request-gate";

test("bounded reads leave request capacity; release is idempotent and FIFO", async () => {
  const gate = new ReadRequestGate(2);
  const signal = new AbortController().signal;
  const first = await gate.enter(signal);
  const second = await gate.enter(signal);
  const order: number[] = [];
  const third = Promise.resolve(gate.enter(signal)).then((release) => {
    order.push(3);
    return release;
  });
  const fourth = Promise.resolve(gate.enter(signal)).then((release) => {
    order.push(4);
    return release;
  });
  await Promise.resolve();
  assert.deepEqual(order, []);
  first();
  (await third)();
  (await fourth)();
  first();
  second();
  assert.deepEqual(order, [3, 4]);
});

test("cancelling queued reads does not fetch or consume the next session's capacity", async () => {
  const gate = new ReadRequestGate(1);
  const first = await gate.enter(new AbortController().signal);
  const controller = new AbortController();
  const queued = Promise.resolve(gate.enter(controller.signal));
  const cancelled = assert.rejects(queued, { name: "AbortError" });
  controller.abort();
  await cancelled;
  first();
  const release = gate.enter(new AbortController().signal);
  assert.equal(typeof release, "function");
  if (typeof release === "function") release();
});
