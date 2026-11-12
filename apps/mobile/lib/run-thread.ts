import type { Run } from "@lonora/contracts";

/** Where the owner reads a run: the origin conversation a run in a hidden work thread
 * reports to (a routine, watch, broker event, Task or their follow-up), except while it
 * waits for the owner's answer, whose question is in its own thread; a run without an
 * origin (an owner's turn, or one from before origins existed) is read in its own thread.
 * The server sets the origin; the client keeps no list of triggers. */
export function reportThread(run: Pick<Run, "thread_id" | "status" | "model_metadata">): string {
  const origin = run.model_metadata?.origin_thread_id;
  return run.status !== "waiting_input" && typeof origin === "string" && origin
    ? origin
    : run.thread_id;
}
