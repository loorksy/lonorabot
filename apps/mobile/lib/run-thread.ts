import type { Run } from "@lonora/contracts";

// Wakes that work in a hidden work thread and report to their agent's conversation.
const REPORTING_WAKES = new Set(["routine", "watch", "broker_event", "follow_up"]);

/** The conversation a run's output reaches: a wake's origin, otherwise its own thread. */
export function reportThread(run: Pick<Run, "thread_id" | "trigger" | "model_metadata">): string {
  const origin = run.model_metadata?.origin_thread_id;
  return REPORTING_WAKES.has(run.trigger) && typeof origin === "string" && origin
    ? origin
    : run.thread_id;
}
