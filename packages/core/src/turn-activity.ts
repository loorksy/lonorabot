/** Actual run/tool observations only. This projection never invents reasoning steps. */
import type { Event, Run, RunStatus } from "@lonora/contracts";
import type { AvatarStateId } from "./trading-avatar-motion";

export type ActivityPhase =
  | "queued"
  | "preparing"
  | "thinking"
  | "searching"
  | "reading"
  | "analyzing"
  | "executing"
  | "learning"
  | "sending"
  | "writing"
  | "waiting_input"
  | "waiting_external"
  | "completed"
  | "failed"
  | "cancelled";
export type ActivityCall = {
  id: string;
  name: string;
  status: "running" | "completed" | "failed" | "cancelled" | "interrupted";
  started_at?: string;
  completed_at?: string;
};
const statuses: Record<string, RunStatus> = {
  "run.queued": "queued",
  "run.leased": "leased",
  "run.recovered": "leased",
  "run.running": "running",
  "run.waiting_input": "waiting_input",
  "run.waiting_takeover": "waiting_takeover",
  "run.completed": "completed",
  "run.failed": "failed",
  "run.cancelled": "cancelled",
};
function validRun(value: unknown): value is Run {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<Run>;
  return (
    typeof row.id === "string" &&
    typeof row.thread_id === "string" &&
    typeof row.agent_id === "string" &&
    typeof row.created_at === "string" &&
    typeof row.updated_at === "string" &&
    typeof row.trigger === "string" &&
    typeof row.model_metadata === "object" &&
    Object.values(statuses).includes(row.status as RunStatus)
  );
}
/** New server projections and lifecycle events update a view without a full-history GET. */
export function projectRunEvents(runs: Run[], events: Event[], threadId?: string): Run[] {
  const rows = new Map<string, Run>();
  for (const row of runs) {
    if (threadId && row.thread_id !== threadId) continue;
    const previous = rows.get(row.id);
    if (!previous || Date.parse(row.updated_at) >= Date.parse(previous.updated_at))
      rows.set(row.id, row);
  }
  for (const event of [...events].sort((a, b) => a.cursor - b.cursor)) {
    if (!event.run_id || (threadId && event.thread_id !== threadId)) continue;
    const snapshot = event.payload.run;
    if (
      validRun(snapshot) &&
      snapshot.id === event.run_id &&
      snapshot.thread_id === event.thread_id &&
      snapshot.agent_id === event.agent_id
    ) {
      const prior = rows.get(snapshot.id);
      if (!prior || Date.parse(snapshot.updated_at) >= Date.parse(prior.updated_at))
        rows.set(snapshot.id, snapshot);
    }
    const row = rows.get(event.run_id),
      status = statuses[event.kind];
    if (!row || !status || Date.parse(event.created_at) < Date.parse(row.updated_at)) continue;
    rows.set(row.id, {
      ...row,
      status,
      updated_at: event.created_at,
      ...(typeof event.payload.code === "string" ? { error_code: event.payload.code } : {}),
    });
  }
  return [...rows.values()].sort((a, b) => a.created_at.localeCompare(b.created_at));
}
function toolPhase(names: string[]): ActivityPhase {
  if (names.some((name) => /^(trade_|goal_step_execute)/.test(name))) return "executing";
  if (names.some((name) => /memory_write|memory_update/.test(name))) return "learning";
  if (names.some((name) => /peer_send|message_send/.test(name))) return "sending";
  if (names.some((name) => /chart_annotat/.test(name))) return "writing";
  if (names.some((name) => /search|recall|retrieve|web_fetch|web_search/.test(name)))
    return "searching";
  if (names.some((name) => /chart_|market_|indicator|workspace_execute/.test(name)))
    return "analyzing";
  return "reading";
}
const avatar: Record<ActivityPhase, AvatarStateId> = {
  queued: "waiting",
  preparing: "thinking",
  thinking: "thinking",
  searching: "searching",
  reading: "inspecting",
  analyzing: "analyzing",
  executing: "executing",
  learning: "learning",
  sending: "sending",
  writing: "writing",
  waiting_input: "reviewing",
  waiting_external: "reviewing",
  completed: "success",
  failed: "error",
  cancelled: "waiting",
};
export function turnActivity(
  run: Run,
  events: Event[],
): { phase: ActivityPhase; avatar: AvatarStateId; calls: ActivityCall[]; observedAt: string } {
  const calls = new Map<string, ActivityCall>();
  let phase: ActivityPhase =
    run.stream?.phase === "streaming" && (run.stream.text || run.stream.rich_content?.parts.length)
      ? "writing"
      : "preparing";
  let observedAt = run.updated_at;
  for (const event of [...events].sort((a, b) => a.cursor - b.cursor)) {
    if (event.run_id !== run.id) continue;
    observedAt = event.created_at;
    if (event.kind === "run.reply_started") phase = "thinking";
    if ((event.kind === "run.delta" && event.payload.text) || event.kind === "run.rich_partial")
      phase = "writing";
    const id = event.payload.call_id;
    if (typeof id !== "string" || !id || !event.kind.startsWith("tool.")) continue;
    const previous = calls.get(id);
    const name =
      (typeof event.payload.name === "string" && event.payload.name.trim()) || previous?.name;
    if (!name) continue;
    if (event.kind === "tool.started")
      calls.set(id, { id, name, status: "running", started_at: event.created_at });
    if (["tool.completed", "tool.failed", "tool.cancelled"].includes(event.kind))
      calls.set(id, {
        ...previous,
        id,
        name,
        status:
          event.kind === "tool.cancelled"
            ? "cancelled"
            : event.kind === "tool.failed" || event.payload.ok === false
              ? "failed"
              : "completed",
        completed_at: event.created_at,
      });
  }
  const active = [...calls.values()].filter((call) => call.status === "running");
  if (active.length) phase = toolPhase(active.map((call) => call.name));
  const stable: Partial<Record<RunStatus, ActivityPhase>> = {
    queued: "queued",
    waiting_input: "waiting_input",
    waiting_takeover: "waiting_external",
    completed: "completed",
    failed: "failed",
    cancelled: "cancelled",
  };
  phase = stable[run.status] ?? phase;
  if (["completed", "failed", "cancelled"].includes(run.status)) {
    for (const call of active) calls.set(call.id, { ...call, status: "interrupted" });
  }
  return { phase, avatar: avatar[phase], calls: [...calls.values()].slice(-24), observedAt };
}
