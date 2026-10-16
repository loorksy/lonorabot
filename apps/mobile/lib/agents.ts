import type { Agent, Thread } from "@lonora/contracts";
import { api } from "./api";

export const agents = {
  list: () => api.get<Agent[]>("/agents"),
  remove: (id: string) => api.delete(`/agents/${encodeURIComponent(id)}`),
  conversation: (id: string) =>
    api.post<Thread>(`/agents/${encodeURIComponent(id)}/conversation`, {}),
  update: (
    id: string,
    body: Pick<
      Agent,
      "name" | "title" | "description" | "avatar" | "color" | "instructions" | "paused"
    >,
  ) => api.patch<Agent>(`/agents/${encodeURIComponent(id)}`, body),
};
