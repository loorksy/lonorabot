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

test("a title copied from the task text follows an edited text", () => {
  const copied = routine("Summarise the market at the open");
  assert.deepEqual(titleInput(copied, "Summarise the market at the close"), {
    title: "Summarise the market at the close",
  });
  // A long text was cut when it was copied: that cut copy is not an own title either.
  const long = "b".repeat(200);
  const cutCopy = routine("b".repeat(160), long);
  assert.deepEqual(titleInput(cutCopy, "short"), { title: "short" });
});

test("prompts compare trimmed: surrounding spaces are not an edit", () => {
  const stored = routine(null, "  Summarise the market at the open \n");
  assert.deepEqual(titleInput(stored, "Summarise the market at the open"), {});
  assert.deepEqual(titleInput(routine("Morning brief"), " Summarise the market at the open "), {});
});

test("the title is cut by code points, never splitting an emoji", () => {
  const text = `${"a".repeat(159)}📈 and more`;
  const { title = "" } = titleInput(null, text);
  assert.equal(Array.from(title).length, 160);
  assert.ok(title.endsWith("📈"));
  assert.ok(!/[\uD800-\uDBFF]$/.test(title));
});
