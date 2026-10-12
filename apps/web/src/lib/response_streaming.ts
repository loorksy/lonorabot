import type { Event } from "./api";
export function streamText(events: Event[], runId: string) {
  const local = events.filter((event) => event.run_id === runId);
  const start = [...local].reverse().find((event) => event.kind === "run.reply_started");
  return local
    .filter((event) => event.kind === "run.delta" && (!start || event.cursor > start.cursor))
    .map((event) => (typeof event.payload.text === "string" ? event.payload.text : ""))
    .join("");
}
