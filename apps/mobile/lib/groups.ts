import type { Group, Thread } from "@lonora/contracts";
import { api } from "./api";

export const groups = {
  get: (id: string) => api.get<Group>(`/groups/${encodeURIComponent(id)}`),
  update: (row: Group, payload: Group["payload"]) =>
    api.put<Group>(`/groups/${encodeURIComponent(row.id)}`, { payload, version: row.version }),
  conversation: async (row: Group) => {
    if (row.state.thread_id)
      return api.get<Thread>(`/threads/${encodeURIComponent(row.state.thread_id)}`);
    const threads = await api.get<Thread[]>("/threads");
    const existing = threads
      .filter((thread) => thread.group_id === row.id)
      .sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
    return existing ?? api.post<Thread>("/threads", { group_id: row.id, title: row.payload.name });
  },
};
