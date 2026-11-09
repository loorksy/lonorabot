import type {
  ChatList,
  Thread,
  ThreadPrefs,
  ThreadPrefsUpdate,
  ThreadSettings,
} from "@lonora/contracts";
import type { ChatRow } from "@lonora/core";
import { api } from "../../lib/api";

/* The owner's conversation state (WP-A) and lists (WP-B) on the server, shared with mobile. */
export const listsApi = {
  prefs: (threadIds: string[], change: ThreadPrefsUpdate) =>
    api.post<ThreadPrefs[]>("/threads/prefs", { thread_ids: threadIds, ...change }),
  read: (threadId: string, seq: number) =>
    api.post<ThreadPrefs>(`/threads/${threadId}/read`, { seq }),
  readAll: () => api.post<ThreadPrefs[]>("/threads/read-all", {}),
  /** «مسح» / «حذف»: the history is hidden for the owner; the thread, grants and agent stay. */
  clear: (threadId: string) => api.post<ThreadPrefs>(`/threads/${threadId}/clear`, {}),
  settings: (settings: ThreadSettings) => api.put<ThreadSettings>("/threads/settings", settings),
  createList: (name: string) => api.post<ChatList>("/chat-lists", { name }),
  renameList: (id: string, name: string) => api.put<ChatList>(`/chat-lists/${id}`, { name }),
  moveList: (id: string, position: number) => api.put<ChatList>(`/chat-lists/${id}`, { position }),
  members: (id: string, threadIds: string[]) =>
    api.put<ChatList>(`/chat-lists/${id}/members`, { thread_ids: threadIds }),
  deleteList: (id: string) => api.delete<{ deleted: boolean }>(`/chat-lists/${id}`),
};

/** A row's canonical conversation; an agent with none gets it now (its pin, mute or list). */
export async function ensureThread(row: ChatRow): Promise<string | null> {
  if (row.threadId) return row.threadId;
  if (row.kind !== "agent") return null;
  const thread = await api.post<Thread>(`/agents/${row.id}/conversation`, {});
  return thread.id;
}
