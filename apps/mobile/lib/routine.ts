import type { Routine, Run } from "@lonora/contracts";
import { api } from "./api";

/** What a save sends; the server keeps fields left out (a one-shot keeps its run_at). */
export type RoutineInput = Partial<
  Pick<
    Routine,
    "title" | "prompt" | "interval_seconds" | "cron" | "run_at" | "timezone" | "enabled"
  >
>;
export const routines = {
  list: (agentId?: string) =>
    api.get<Routine[]>(`/routines${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ""}`),
  create: (agentId: string, input: RoutineInput) =>
    api.post<Routine>(`/routines/${encodeURIComponent(agentId)}`, input),
  update: (row: Routine, input: RoutineInput) =>
    api.put<Routine>(`/routines/${encodeURIComponent(row.id)}`, input),
  remove: (id: string) => api.delete(`/routines/${encodeURIComponent(id)}`),
  history: (id: string) => api.get<Run[]>(`/routines/${encodeURIComponent(id)}/history`),
};
