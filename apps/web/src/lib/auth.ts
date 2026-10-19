import type { Owner } from "@lonora/contracts";
import { api, resetSessionRequests } from "./api";

export type { Owner } from "@lonora/contracts";
export const auth = {
  session: () => api.get<Owner>("/auth/session"),
  login: async (email: string, password: string) => {
    resetSessionRequests();
    return api.post<{ owner: Owner; csrf: string }>("/auth/login", { email, password });
  },
  logout: async () => {
    resetSessionRequests();
    const result = await api.post<{ logged_out: boolean }>("/auth/logout", {});
    resetSessionRequests();
    return result;
  },
};
