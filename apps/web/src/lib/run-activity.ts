import type { AvatarStateId } from "@lonora/core";
import type { Event, Run } from "./api";

export function runActivity(run: Run, events: Event[]): AvatarStateId {
  if (run.status === "queued") return "waiting";
  if (run.status === "failed") return "error";
  if (run.status.startsWith("waiting")) return "reviewing";
  if (run.status === "completed") return "success";
  if (run.status === "cancelled") return "waiting";
  const active = new Map<string, string>();
  let phase: AvatarStateId = "thinking";
  for (const event of events) {
    if (event.run_id !== run.id) continue;
    if (event.kind === "run.reply_started") phase = "thinking";
    if (event.kind === "run.delta" && event.payload.text) phase = "writing";
    const id = String(event.payload.call_id ?? "");
    if (event.kind === "tool.started") active.set(id, String(event.payload.name ?? ""));
    if (["tool.completed", "tool.cancelled"].includes(event.kind)) active.delete(id);
  }
  const names = [...active.values()];
  if (names.some((name) => /^(trade_|goal_step_execute)/.test(name))) return "executing";
  if (names.some((name) => /memory_write|memory_update/.test(name))) return "learning";
  if (names.some((name) => /peer_send|message_send/.test(name))) return "sending";
  if (names.some((name) => /chart_annotat/.test(name))) return "writing";
  if (names.some((name) => /search|recall|retrieve/.test(name))) return "searching";
  if (names.some((name) => /chart_|account_read|market_|indicator/.test(name))) return "analyzing";
  return names.length ? "inspecting" : phase;
}
