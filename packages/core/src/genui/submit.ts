/** Card locks, never-run marks and send availability, shared by web and mobile
 * (GENUI_PLAN §8.1, §8.2 rules N and T, §9.3). Derived from the messages and Runs the client
 * already follows; the server applies the same rules on write and on read. */
import type { Message, Run } from "@lonora/contracts";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
const WAITING = new Set(["waiting_input", "waiting_takeover"]);

/** «مُعدّلة» (superseded by «تعديل») or «لم يُنفَّذ» (its Run ended without starting).
 * Only the server's record of that fact counts, never a Run's status seen here: a copy of
 * the message older than the Run's start would make a send that ran look never run, and
 * unlock its card (review U1). */
export function submitMark(message: Message): "superseded" | "not_run" | null {
  if (message.origin !== "ui_submit" || !message.ui_submit) return null;
  if (message.ui_submit.started_at) return null;
  return message.ui_submit.mark ?? message.ui_mark ?? null;
}

/** The locking submission of one card part, or null. */
export function cardLock(
  card: Message,
  part: number,
  messages: readonly Message[],
): { id: string; seq: number } | null {
  const unlocked = Number(card.ui_state?.parts?.[String(part)]?.unlocked_seq ?? 0);
  let lock: { id: string; seq: number } | null = null;
  for (const message of messages) {
    if (
      message.origin !== "ui_submit" ||
      message.reply_to !== card.id ||
      !message.ui_submit?.lock ||
      message.ui_submit.part !== part ||
      message.seq <= unlocked ||
      submitMark(message)
    )
      continue;
    if (!lock || message.seq > lock.seq) lock = { id: message.id, seq: message.seq };
  }
  const derived = card.ui_lock?.[String(part)];
  if (!lock && derived && !messages.some((message) => message.id === derived.message_id)) {
    // The page that carried the submission is not loaded: the server's derived lock holds.
    return { id: derived.message_id, seq: derived.seq };
  }
  return lock;
}

/** Why a send button is disabled right now, or null when it may send (§8.1). */
export function sendBlocked(
  agentId: string | null | undefined,
  threadId: string,
  messages: readonly Message[],
  runs: readonly Run[],
  paused: boolean,
): "paused" | "waiting" | "queued" | null {
  if (paused) return "paused";
  if (!agentId) return null;
  const mine = runs.filter((run) => run.thread_id === threadId && run.agent_id === agentId);
  if (mine.some((run) => WAITING.has(run.status))) return "waiting";
  const queued = messages.some(
    (message) =>
      message.origin === "ui_submit" &&
      message.ui_submit &&
      !message.ui_submit.started_at &&
      mine.some((run) => run.id === message.ui_submit?.run_id && !TERMINAL.has(run.status)),
  );
  return queued ? "queued" : null;
}
