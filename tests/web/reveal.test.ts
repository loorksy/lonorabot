import assert from "node:assert/strict";
import { test } from "node:test";
import { nextReveal, REVEAL_LAG, revealDelay, revealParts } from "../../apps/web/src/lib/reveal";

/* The pacing of a streaming reply (reference streamAnswer, Desktop-37 5806-5830). */
test("a reply is revealed a word and its gap at a time, between 34 and 68 ms", () => {
  assert.deepEqual(revealParts("a b  c"), ["a", " ", "b", "  ", "c"]);
  assert.equal(revealParts("a b  c").join(""), "a b  c");
  assert.equal(nextReveal(0, 10), 2);
  assert.equal(nextReveal(4, 10), 6);
  assert.equal(nextReveal(9, 10), 10);
  assert.equal(nextReveal(10, 10), 10);
  assert.equal(revealDelay(0), 34);
  assert.equal(revealDelay(1), 68);
});

test("the reveal never trails what has arrived by more than the lag", () => {
  // A large piece arriving at once (a reload, a fast model) is mostly shown at once.
  assert.equal(nextReveal(0, 400), 400 - REVEAL_LAG);
  assert.equal(nextReveal(390, 400), 392);
  assert.equal(nextReveal(0, 400, 10), 390);
});
