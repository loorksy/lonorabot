import type { Owner } from "@lonora/contracts";
import { api } from "./api";

export type { Owner } from "@lonora/contracts";
export const auth = {
  session: () => api.get<Owner>("/auth/session"),
  login: (email: string, password: string) =>
    api.post<{ owner: Owner; csrf: string }>("/auth/login", { email, password }),
  logout: () => api.post<{ logged_out: boolean }>("/auth/logout", {}),
};
