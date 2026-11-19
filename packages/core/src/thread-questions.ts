import type { InputRequest, Run } from "@lonora/contracts";

/** The questions shown in one thread, keyed by the message that holds each.
 *
 * A run asks where it reports: a background run working in a hidden thread has its
 * question copied into the conversation it reports to, and the request names that
 * thread. A request without one (stored before) is in its run's own thread. A later row
 * replaces an earlier one for the same message. */
export function threadQuestions(runs: readonly Run[], threadId: string): Map<string, InputRequest> {
  const questions = new Map<string, InputRequest>();
  for (const run of runs) {
    for (const request of run.input_requests ?? []) {
      if ((request.thread_id ?? run.thread_id) === threadId) {
        questions.set(request.message_id, request);
      }
    }
  }
  return questions;
}
