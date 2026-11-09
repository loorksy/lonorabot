import type { Agent, Thread } from "@lonora/contracts";
import { api } from "./api";

export const agents = {
  list: () => api.get<Agent[]>("/agents"),
  conversation: (id: string) =>
    api.post<Thread>(`/agents/${encodeURIComponent(id)}/conversation`, {}),
  update: (
    id: string,
    body: Partial<
      Pick<Agent, "name" | "title" | "description" | "avatar" | "color" | "instructions" | "paused">
    > & {
      scope_mode?: "flexible";
      trading_account_id?: string | null;
      trading_symbol?: string | null;
      expected_scope_revision?: number;
    },
  ) => api.patch<Agent>(`/agents/${encodeURIComponent(id)}`, body),
};
