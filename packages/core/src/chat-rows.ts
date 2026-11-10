/**
 * The conversation list's rows, filters and selection arithmetic, shared by Web and
 * Mobile. A row is every agent and every group, with the owner's state of its canonical
 * conversation when one exists (the inbox projection). The order is the reference's:
 * pinned first in pin order, then the latest message (one still in this device's outbox
 * counts the moment it is written; a chat with no visible message sorts last), then the
 * agents before the groups as the server lists them. Nothing here is stored or fetched.
 */
import type { Agent, AttentionImportance, ChatList, InboxEntry, Resource } from "@lonora/contracts";
import { inboxUnread, isUnread } from "./inbox";

/** The built-in filters of the list, then the owner's lists as `list:<id>`. */
export type ListFilter = "all" | "unread" | "fav" | "agents" | "groups" | `list:${string}`;
export const BUILTIN_FILTERS = ["all", "unread", "fav", "agents", "groups"] as const;
/** The pin limit the server enforces (409 thread_pin_limit). */
export const PIN_LIMIT = 3;

export type ChatRowKind = "agent" | "group";
export type ChatRow = {
  /** `agent:<id>` or `group:<id>`: the key the list, the selection and the lists share. */
  key: string;
  kind: ChatRowKind;
  id: string;
  agent?: Agent;
  group?: Resource;
  /** The canonical conversation and the owner's state of it, when one exists. */
  entry?: InboxEntry;
  threadId?: string;
  name: string;
  /** What line 2 says before anything was said: the agent's role or the group's purpose. */
  subtitle: string;
  paused: boolean;
  /** The latest message's time; "" when the chat has none to show. */
  lastActivityAt: string;
};
/** The newest message this device still holds in its outbox for a thread, if any. */
export type OutboxLatest = (threadId: string) => string | undefined;

export const rowKey = (kind: ChatRowKind, id: string) => `${kind}:${id}`;

const text = (value: unknown) => (typeof value === "string" ? value : "");

const latest = (...times: (string | undefined)[]) =>
  times.reduce<string>((max, time) => (time && time > max ? time : max), "");

export function chatRows(
  agents: readonly Agent[],
  groups: readonly Resource[],
  entries: readonly InboxEntry[],
  outbox?: OutboxLatest,
): ChatRow[] {
  const byEntity = new Map<string, InboxEntry>();
  for (const entry of entries) {
    const key = entry.agent_id
      ? rowKey("agent", entry.agent_id)
      : entry.group_id
        ? rowKey("group", entry.group_id)
        : null;
    if (key && !byEntity.has(key)) byEntity.set(key, entry);
  }
  const rows: ChatRow[] = [
    ...agents.map((agent): ChatRow => {
      const key = rowKey("agent", agent.id);
      const entry = byEntity.get(key);
      return {
        key,
        kind: "agent",
        id: agent.id,
        agent,
        entry,
        threadId: entry?.thread_id,
        name: agent.name,
        subtitle: agent.title || agent.description || "",
        paused: agent.paused,
        lastActivityAt: latest(entry?.last_message?.created_at, entry && outbox?.(entry.thread_id)),
      };
    }),
    ...groups.map((group): ChatRow => {
      const key = rowKey("group", group.id);
      const entry = byEntity.get(key);
      const stateThread = text(group.state?.thread_id);
      const threadId = entry?.thread_id ?? (stateThread || undefined);
      return {
        key,
        kind: "group",
        id: group.id,
        group,
        entry,
        threadId,
        name: text(group.payload.name),
        subtitle: text(group.payload.purpose),
        paused: false,
        lastActivityAt: latest(
          entry?.last_message?.created_at,
          threadId ? outbox?.(threadId) : undefined,
        ),
      };
    }),
  ];
  return rows
    .map((row, index) => ({ row, index }))
    .sort((first, second) => {
      const pinA = pinIndex(first.row);
      const pinB = pinIndex(second.row);
      if (pinA !== pinB) return pinA - pinB;
      if (first.row.lastActivityAt !== second.row.lastActivityAt)
        return first.row.lastActivityAt < second.row.lastActivityAt ? 1 : -1;
      return first.index - second.index;
    })
    .map(({ row }) => row);
}

const pinIndex = (row: ChatRow) =>
  !isArchived(row) && row.entry?.pinned_order != null
    ? row.entry.pinned_order
    : Number.MAX_SAFE_INTEGER;
export const isArchived = (row: ChatRow) => Boolean(row.entry?.archived);
export const isPinned = (row: ChatRow) => pinIndex(row) !== Number.MAX_SAFE_INTEGER;
export const isMuted = (row: ChatRow) => Boolean(row.entry?.muted);
export const isFavourite = (row: ChatRow) => Boolean(row.entry?.favourite);
export const rowUnread = (row: ChatRow) => (row.entry ? inboxUnread(row.entry) : 0);
export const rowIsUnread = (row: ChatRow) => Boolean(row.entry && isUnread(row.entry));
/** The 12px dot: marked unread with no new message. */
export const rowMarkedOnly = (row: ChatRow) =>
  Boolean(row.entry && row.entry.unread_count === 0 && row.entry.marked_unread);
/** The count pill: the agent's messages after the read cursor. */
export const rowCount = (row: ChatRow) => row.entry?.unread_count ?? 0;

export const listIdOf = (filter: ListFilter) =>
  filter.startsWith("list:") ? filter.slice("list:".length) : null;

/** The main list under one filter: archived rows never appear in it. */
export function filterRows(
  rows: readonly ChatRow[],
  filter: ListFilter,
  lists: readonly ChatList[] = [],
): ChatRow[] {
  const listId = listIdOf(filter);
  const members = listId
    ? new Set(lists.find((list) => list.id === listId)?.thread_ids ?? [])
    : null;
  return rows.filter((row) => {
    if (isArchived(row)) return false;
    switch (filter) {
      case "all":
        return true;
      case "unread":
        return rowIsUnread(row);
      case "fav":
        return isFavourite(row);
      case "agents":
        return row.kind === "agent";
      case "groups":
        return row.kind === "group";
      default:
        return Boolean(members && row.threadId && members.has(row.threadId));
    }
  });
}

export const archivedRows = (rows: readonly ChatRow[]) => rows.filter(isArchived);

/** The «المؤرشفة» row: the archived count, and how many of them are unread. */
export function archivedRowSummary(rows: readonly ChatRow[]) {
  const archived = archivedRows(rows);
  return { count: archived.length, unread: archived.filter(rowIsUnread).length };
}

/** A list chip's members that are still rows (an agent or group that exists). */
export function listMemberRows(rows: readonly ChatRow[], list: ChatList): ChatRow[] {
  const members = new Set(list.thread_ids);
  return rows.filter((row) => row.threadId && members.has(row.threadId));
}

/** What the selection toolbar and its ⋮ menu offer for the picked rows. */
export function selectionSummary(picked: readonly ChatRow[], visibleKeys: readonly string[]) {
  const keys = new Set(picked.map((row) => row.key));
  return {
    count: picked.length,
    allPinned: picked.length > 0 && picked.every(isPinned),
    allMuted: picked.length > 0 && picked.every(isMuted),
    anyUnread: picked.some(rowIsUnread),
    allFavourite: picked.length > 0 && picked.every(isFavourite),
    allVisiblePicked: visibleKeys.every((key) => keys.has(key)),
    agentRows: picked.filter((row) => row.kind === "agent"),
    groupRows: picked.filter((row) => row.kind === "group"),
  };
}

/** Pins after pinning every picked row that is not pinned yet; more than 3 is refused. */
export function pinsAfter(rows: readonly ChatRow[], picked: readonly ChatRow[]) {
  return rows.filter(isPinned).length + picked.filter((row) => !isPinned(row)).length;
}

/** «مجموعة من المحددين»: the new group's name, from up to three of the agents' names. */
export const groupDraftName = (names: readonly string[]) =>
  names.filter(Boolean).slice(0, 3).join("، ");

/**
 * Owner decision Q6: the offline queue flushes by itself only plain messages that never
 * received a server response; an input answer, an approval or an owner decision never
 * waits in it and stays «failed» with a manual retry under the same client_nonce.
 */
export function isPlainOutgoing(body: Readonly<Record<string, unknown>>): boolean {
  // A card's send is never flushed by itself either (GENUI_PLAN §8.6).
  return body.input_answer == null && body.ui_submit == null;
}

/**
 * Owner decision Q4: mute and archive suppress the heads-up of a message (and its sound
 * and badge); a critical or action_required attention item always shows.
 */
export const headsUpAllowed = (entry: InboxEntry | undefined) => !entry?.muted && !entry?.archived;
/** The owner's quiet hours (the reach-me policy) in the owner's time zone, crossing midnight
 * when the start is later than the end. Minutes after midnight (Q47) when the server sent
 * them, else whole hours. No window set, no quiet. */
export type QuietHours = {
  quiet_start_hour: number | null;
  quiet_end_hour: number | null;
  quiet_start_minute?: number | null;
  quiet_end_minute?: number | null;
  timezone: string;
};
export function inQuietHours(policy: QuietHours | null | undefined, now: Date): boolean {
  if (!policy) return false;
  const start =
    policy.quiet_start_minute ??
    (policy.quiet_start_hour == null ? null : policy.quiet_start_hour * 60);
  const end =
    policy.quiet_end_minute ?? (policy.quiet_end_hour == null ? null : policy.quiet_end_hour * 60);
  if (start == null || end == null || start === end) return false;
  let minute: number;
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      hour: "numeric",
      minute: "numeric",
      hourCycle: "h23",
      timeZone: policy.timezone,
    }).formatToParts(now);
    const part = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
    minute = (part("hour") % 24) * 60 + part("minute");
  } catch {
    minute = now.getUTCHours() * 60 + now.getUTCMinutes();
  }
  return start < end ? minute >= start && minute < end : minute >= start || minute < end;
}
export const attentionAlwaysShows = (importance: AttentionImportance) =>
  importance === "critical" || importance === "action_required";
