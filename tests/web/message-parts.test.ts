import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  callPart,
  pendingVoiceRich,
  validateAgentRichContent,
  voicePart,
} from "../../packages/core/src/message-parts";
import { validateRichContent } from "../../packages/core/src/visual-response";

const artifact = "11111111-2222-4333-8444-555555555555";
const peaks = Array.from({ length: 44 }, (_, index) => index * 2);
const voice = {
  type: "voice",
  artifact_id: artifact,
  duration: 7.5,
  peaks,
  transcript_status: "done",
};
const call = { type: "call", direction: "incoming", duration_seconds: 0, missed: true };

test("voice and call parts validate and are read back by their helpers", () => {
  assert.deepEqual(validateRichContent({ version: 1, parts: [voice] })?.parts, [voice]);
  assert.deepEqual(voicePart({ rich_content: { version: 1, parts: [voice] } } as never), voice);
  assert.deepEqual(callPart({ rich_content: { version: 1, parts: [call] } } as never), call);
  assert.equal(voicePart({ rich_content: { version: 1, parts: [call] } } as never), null);
  assert.equal(callPart({ rich_content: null }), null);
});

test("malformed voice and call parts fail closed", () => {
  const bad = [
    { ...voice, peaks: peaks.slice(1) },
    { ...voice, peaks: [...peaks.slice(1), 101] },
    { ...voice, peaks: [...peaks.slice(1), 1.5] },
    { ...voice, duration: 0 },
    { ...voice, duration: 121 },
    { ...voice, artifact_id: "not-a-uuid" },
    { ...voice, transcript_status: "unknown" },
    { ...voice, src: "data:audio/webm;base64,AAAA" },
    { ...call, direction: "sideways" },
    { ...call, duration_seconds: -1 },
    { ...call, duration_seconds: 1.5 },
    { ...call, missed: "yes" },
  ];
  for (const part of bad) assert.equal(validateRichContent({ version: 1, parts: [part] }), null);
});

test("an agent reply can never carry a server-written part", () => {
  const text = { type: "text", text: "مرحبا" };
  assert.ok(validateAgentRichContent({ version: 1, parts: [text] }));
  assert.equal(validateAgentRichContent({ version: 1, parts: [text, voice] }), null);
  assert.equal(validateAgentRichContent({ version: 1, parts: [call] }), null);
});

test("a sending or failed voice note carries its voice part, so it is never a blank bubble", () => {
  const rich = pendingVoiceRich({
    content: "",
    voice: { artifact_id: artifact, duration: 3.4, peaks },
  });
  const part = voicePart({ rich_content: rich });
  assert.equal(part?.artifact_id, artifact);
  assert.equal(part?.duration, 3.4);
  assert.equal(part?.transcript_status, "pending");
  assert.equal(pendingVoiceRich({ content: "hello" }), null);
  // The web and mobile outboxes both draw the pending bubble from it.
  for (const path of [
    "apps/web/src/lib/outgoing-messages.ts",
    "apps/mobile/lib/outgoing-messages.ts",
  ])
    assert.match(readFileSync(path, "utf8"), /rich_content: pendingVoiceRich\(body\)/);
  // Mobile names a voice note or a call log instead of drawing an empty bubble.
  const bubble = readFileSync("apps/mobile/components/message-bubble.tsx", "utf8");
  assert.match(bubble, /voicePart\(message\)/);
  assert.match(bubble, /callPart\(message\)/);
});
