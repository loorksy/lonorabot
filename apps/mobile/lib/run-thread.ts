import type { Run } from "@lonora/contracts";

/** Where the owner reads a run. A run waiting on its question opens the thread that holds
 * the question: the conversation a background run's question is copied into, or the run's
 * own thread for a question asked before copies existed. Otherwise a run in a hidden work
 * thread opens the origin conversation it reports to (a routine, watch, broker event, Task
 * or their follow-up), and a run without an origin (an owner's turn, or one from before
 * origins existed) opens its own thread. The server sets these; the client keeps no list
 * of triggers. */
export function reportThread(
  run: Pick<Run, "thread_id" | "status" | "model_metadata" | "input_request">,
): string {
  const question = run.input_request;
  if (run.status === "waiting_input" && question?.status === "pending") {
    return question.thread_id ?? run.thread_id;
  }
  const origin = run.model_metadata?.origin_thread_id;
  return typeof origin === "string" && origin ? origin : run.thread_id;
}
