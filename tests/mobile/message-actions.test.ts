// The message menu's rules on mobile, as on Web: what «تعديل وإعادة الإرسال» and «تحويل إلى مهمة»
// apply to, and the owner's one quick reaction per message.
import assert from "node:assert/strict";
import test from "node:test";
import {
  canEditAndResend,
  canTurnIntoTask,
  ownerReaction,
  taskFromMessage,
  withOwnerReaction,
} from "../../apps/mobile/lib/message-actions";
import type { Message, MessageReaction } from "../../packages/contracts/src";

const base: Message = {
  id: "m1",
  thread_id: "t1",
  agent_id: null,
  seq: 4,
  role: "user",
  content: "Buy gold at 2,400",
  reply_to: null,
  attachment_ids: [],
  created_at: "2026-11-12T06:00:00Z",
};

test("only the owner's own plain text can be edited and resent", () => {
  assert.equal(canEditAndResend(base), true);
  assert.equal(canEditAndResend({ ...base, role: "assistant" }), false);
  assert.equal(canEditAndResend({ ...base, attachment_ids: ["f1"] }), false);
  assert.equal(canEditAndResend({ ...base, superseded_by: "m2" }), false);
  assert.equal(canEditAndResend({ ...base, origin: "ui_submit" }), false);
  assert.equal(canEditAndResend({ ...base, id: "pending:n1" }), false);
  assert.equal(
    canEditAndResend({
      ...base,
      content: "",
      rich_content: {
        version: 1,
        parts: [{ type: "voice", artifact_id: "v", duration: 3, peaks: [] }],
      } as Message["rich_content"],
    }),
    false,
  );
});

test("a task comes from a text message, never from a card, a voice note or files", () => {
  assert.equal(canTurnIntoTask(base), true);
  assert.equal(canTurnIntoTask({ ...base, role: "assistant", agent_id: "a1" }), true);
  assert.equal(canTurnIntoTask({ ...base, attachment_ids: ["f1"] }), false);
  assert.equal(canTurnIntoTask({ ...base, content: "  " }), false);
  assert.equal(canTurnIntoTask({ ...base, id: "pending:n1" }), false);
  assert.equal(
    canTurnIntoTask({
      ...base,
      role: "assistant",
      rich_content: {
        version: 1,
        parts: [
          { type: "ui", document: { version: 1, root: { id: "r", type: "text", text: "x" } } },
        ],
      } as unknown as Message["rich_content"],
    }),
    false,
  );
  const long = "x".repeat(400);
  assert.deepEqual(taskFromMessage({ ...base, content: long }), {
    title: "x".repeat(160),
    description: long,
  });
});

test("the owner holds one quick reaction per message; a second replaces it, null removes it", () => {
  const agent: MessageReaction = { reactor: "a1", emoji: "👍", created_at: "t" };
  const rows = withOwnerReaction([agent], "❤️", "now");
  assert.deepEqual(
    rows.map((row) => [row.reactor, row.emoji]),
    [
      ["a1", "👍"],
      ["owner", "❤️"],
    ],
  );
  assert.equal(ownerReaction(rows), "❤️");
  const replaced = withOwnerReaction(rows, "🙏", "later");
  assert.equal(replaced.filter((row) => row.reactor === "owner").length, 1);
  assert.equal(ownerReaction(replaced), "🙏");
  assert.deepEqual(withOwnerReaction(replaced, null, "x"), [agent]);
  assert.equal(ownerReaction(undefined), null);
});
