/**
 * The conversation list's shared arithmetic: unread per row, the Chats badge, the
 * «المؤرشفة» row and the list order, from the server's inbox projection. Web and Mobile
 * compute the same numbers from the same entries; nothing here is stored.
 */
import type { InboxEntry, ThreadPrefs } from "@lonora/contracts";

/** The count pill, or 1 for a conversation marked unread with no new messages. */
export function inboxUnread(entry: InboxEntry): number {
  if (entry.unread_count > 0) return entry.unread_count;
  return entry.marked_unread ? 1 : 0;
}

export function isUnread(entry: InboxEntry): boolean {
  return inboxUnread(entry) > 0;
}

/** The Chats tab and rail badge: unread over conversations neither archived nor muted. */
export function unreadBadgeTotal(entries: readonly InboxEntry[]): number {
  let total = 0;
  for (const entry of entries) {
    if (!entry.archived && !entry.muted) total += inboxUnread(entry);
  }
  return total;
}

/** The «المؤرشفة» row: how many are archived and how many of those are unread. */
export function archivedSummary(entries: readonly InboxEntry[]): { count: number; unread: number } {
  let count = 0;
  let unread = 0;
  for (const entry of entries) {
    if (!entry.archived) continue;
    count += 1;
    if (isUnread(entry)) unread += 1;
  }
  return { count, unread };
}

/** Pinned first in pin order, then latest activity first; ties by thread id. */
export function orderInbox(entries: readonly InboxEntry[]): InboxEntry[] {
  return [...entries].sort((first, second) => {
    const firstPin = first.pinned_order ?? Number.MAX_SAFE_INTEGER;
    const secondPin = second.pinned_order ?? Number.MAX_SAFE_INTEGER;
    if (firstPin !== secondPin) return firstPin - secondPin;
    if (first.last_activity_at !== second.last_activity_at)
      return first.last_activity_at < second.last_activity_at ? 1 : -1;
    return first.thread_id < second.thread_id ? -1 : first.thread_id > second.thread_id ? 1 : 0;
  });
}

/** An inbox entry with the owner's new state of its conversation, merged before the next refetch. */
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
