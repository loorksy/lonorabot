import type { Agent, Thread } from "@lonora/contracts";
import { api } from "./api";

export const agents = {
  list: () => api.get<Agent[]>("/agents"),
  conversation: (id: string) =>
    api.post<Thread>(`/agents/${encodeURIComponent(id)}/conversation`, {}),
  update: (
    id: string,
    body: Pick<Agent, "name" | "avatar" | "color" | "instructions" | "paused">,
  ) => api.patch<Agent>(`/agents/${encodeURIComponent(id)}`, body),
};
