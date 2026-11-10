import assert from "node:assert/strict";
import { test } from "node:test";
import type { Routine } from "@lonora/contracts";
import { titleInput } from "../../apps/mobile/lib/routine-title";

const routine = (title: string | null, prompt = "Summarise the market at the open") =>
  ({ id: "r1", title, prompt }) as unknown as Routine;

test("a save keeps a title already set, whoever set it", () => {
  // A switch flip or a timezone change leaves the text as it is: no title is sent.
  assert.deepEqual(titleInput(routine("Morning brief"), "Summarise the market at the open"), {});
  // Even an edited text keeps the routine's own title (an agent's or the owner's).
  assert.deepEqual(titleInput(routine("Morning brief"), "Something new"), {});
  // No title of its own and an unedited text: the prompt is never sent as its name.
  assert.deepEqual(titleInput(routine(null), "Summarise the market at the open"), {});
});

test("a new routine, or an edited one with no title, is named after its text", () => {
  assert.deepEqual(titleInput(null, "Weekly report"), { title: "Weekly report" });
  assert.deepEqual(titleInput(routine(""), "Weekly report"), { title: "Weekly report" });
});

test("the title is cut by code points, never splitting an emoji", () => {
  const text = `${"a".repeat(159)}📈 and more`;
  const { title = "" } = titleInput(null, text);
  assert.equal(Array.from(title).length, 160);
  assert.ok(title.endsWith("📈"));
  assert.ok(!/[\uD800-\uDBFF]$/.test(title));
});
