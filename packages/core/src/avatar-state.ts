import type { AvatarStateId } from "./trading-avatar-motion";

/** Visual state is a projection of observed activity, never a simulated job sequence. */
export function avatarState({
  working = false,
  waiting = false,
  error = false,
  voice,
}: {
  working?: boolean;
  waiting?: boolean;
  error?: boolean;
  voice?: { connected: boolean; phase: "listening" | "speaking"; muted: boolean; ending?: boolean };
} = {}): AvatarStateId {
  if (error) return "error";
  if (voice) {
    if (voice.ending) return "waiting";
    if (!voice.connected) return "connecting";
    if (voice.phase === "speaking") return "speaking";
    return voice.muted ? "waiting" : "listening";
  }
  if (waiting) return "reviewing";
  return working ? "working" : "waiting";
}
