import { createContext, useContext } from "react";
import type { Agent, Owner, Resource, Run } from "../lib/api";
import type { InboxEntry } from "../pages/shell/conversation-inbox";

/** What the shell fetched once for every pane, including a pager ghost. */
export type ShellData = {
  owner: Owner;
  agents: Agent[];
  agentsLoading: boolean;
  groups: Resource[];
  groupsLoading: boolean;
  inbox: InboxEntry[];
  inboxLoading: boolean;
  inboxError: unknown;
  error: unknown;
  runs: Run[];
  busyIds: Set<string>;
  refresh: () => void;
  createAgent: ReturnType<typeof import("../hooks/useAgents").useAgents>["create"];
  removeAgent: (id: string) => Promise<void>;
  addGroup: (group: Resource) => void;
  signOut: () => Promise<void>;
};
const Context = createContext<ShellData | null>(null);
export const ShellDataProvider = Context.Provider;
export function useShellData() {
  const value = useContext(Context);
  if (!value) throw new Error("shell_data_missing");
  return value;
}
