import { createContext, useContext } from "react";
import type {
  Agent,
  ChatList,
  InboxEntry,
  Owner,
  Resource,
  Run,
  ThreadPrefs,
  ThreadSettings,
} from "../lib/api";

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
  /** The owner's lists (WP-B), shared with mobile. */
  chatLists: ChatList[];
  /** «إبقاء المحادثات مؤرشفة»; null until read. */
  threadSettings: ThreadSettings | null;
  error: unknown;
  runs: Run[];
  busyIds: Set<string>;
  refresh: () => void;
  /** The server's answer to a prefs, read or clear request, merged before the next refetch. */
  patchInbox: (prefs: ThreadPrefs[]) => void;
  setChatLists: (update: (lists: ChatList[]) => ChatList[]) => void;
  setThreadSettings: (settings: ThreadSettings) => void;
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

/** An inbox entry with the owner's new state of its conversation. */
export function mergePrefs(entries: InboxEntry[], prefs: ThreadPrefs[]): InboxEntry[] {
  const byThread = new Map(prefs.map((row) => [row.thread_id, row]));
  return entries.map((entry) => {
    const next = byThread.get(entry.thread_id);
    if (!next) return entry;
    const { thread_id: _thread, updated_at: _updated, ...state } = next;
    const hidden = next.hidden_before_seq > entry.hidden_before_seq;
    return {
      ...entry,
      ...state,
      // Nothing hidden can be unread, and «مسح» empties the preview until the refetch.
      unread_count:
        next.last_read_seq >= (entry.last_message?.seq ?? 0) || hidden ? 0 : entry.unread_count,
      last_message:
        hidden && entry.last_message && entry.last_message.seq <= next.hidden_before_seq
          ? null
          : entry.last_message,
    };
  });
}
