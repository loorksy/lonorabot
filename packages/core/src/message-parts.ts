/** Server-written message parts: an owner voice note and a call log bubble (WP-E). */
import type { CallPart, Message, RichContent, VoicePart } from "@lonora/contracts";
import { validateRichContent } from "./visual-response";

type WithRich = Pick<Message, "rich_content">;

/** The validated voice part of an owner voice note, else null. */
export function voicePart(message: WithRich): VoicePart | null {
  const part = validateRichContent(message.rich_content)?.parts.find(
    (item) => item.type === "voice",
  );
  return part?.type === "voice" ? part : null;
}

/** The validated call part of a call log system message, else null. */
export function callPart(message: WithRich): CallPart | null {
  const part = validateRichContent(message.rich_content)?.parts.find(
    (item) => item.type === "call",
  );
  return part?.type === "call" ? part : null;
}

/** Rich content an Agent reply may carry: voice and call parts are server-written only. */
export function validateAgentRichContent(value: unknown): RichContent | null {
  const rich = validateRichContent(value);
  return rich?.parts.every((part) => part.type === "text" || part.type === "ui") ? rich : null;
}

/** The voice part a voice note's send body carries, as the rich content of its pending or failed
    bubble, so it is drawn as a voice note before the server's copy arrives. Null otherwise. */
export function pendingVoiceRich(body: Record<string, unknown>): RichContent | null {
  const voice = body.voice as { artifact_id?: unknown; duration?: unknown; peaks?: unknown } | null;
  if (!voice || typeof voice !== "object" || typeof voice.artifact_id !== "string") return null;
  return validateRichContent({
    version: 1,
    parts: [
      {
        type: "voice",
        artifact_id: voice.artifact_id,
        duration: Number(voice.duration),
        peaks: Array.isArray(voice.peaks) ? voice.peaks : [],
        transcript_status: "pending",
      },
    ],
  });
}
