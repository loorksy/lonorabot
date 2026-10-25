import type { Message, Run } from "./api";

/** Failures belong to the owner's actual input, never to a background activity footer. */
export function failedReplies(runs: Run[], messages: Message[]) {
  const inputs = messages.filter(
    (message) => message.role === "user" && !message.id.startsWith("pending:"),
  );
  return runs.flatMap((run) => {
    if (run.status !== "failed" || !["user", "group"].includes(run.trigger) || run.parent_run_id)
      return [];
    const message = inputs
      .filter((input) => input.thread_id === run.thread_id)
      .filter((input) =>
        run.input_seq != null
          ? input.seq === run.input_seq
          : Date.parse(input.created_at) <= Date.parse(run.created_at),
      )
      .sort((a, b) => b.seq - a.seq)[0];
    return message ? [{ run, message }] : [];
  });
}
