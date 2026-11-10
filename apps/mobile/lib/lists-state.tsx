// The list's state shared by the chats tab, the archived page and the header: the rows, the
// active filter and the selection. Every change of a conversation's state goes to the server
// and comes back merged (the same contract as Web's lists/state).
import type { ThreadPrefs, ThreadPrefsUpdate } from "@lonora/contracts";
import { type ChatRow, chatRows, type ListFilter } from "@lonora/core";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { BackHandler } from "react-native";
import { useToast } from "../components/shell/toast";
import { ApiError } from "./api";
import { ensureThread, listsApi } from "./lists-api";
import {
  hydrateOutgoing,
  type OutgoingIntent,
  outgoingKey,
  outgoingMessages,
  subscribeOutgoing,
} from "./outgoing-messages";
import { useSession } from "./session";
import { useShellData } from "./shell-data";

type Lists = {
  rows: ChatRow[];
  filter: ListFilter;
  setFilter: (filter: ListFilter) => void;
  selected: ReadonlySet<string> | null;
  picked: ChatRow[];
  start: (key: string) => void;
  toggle: (key: string) => void;
  selectAll: (keys: readonly string[]) => void;
  end: () => void;
  prefs: (rows: readonly ChatRow[], change: ThreadPrefsUpdate) => Promise<void>;
  read: (rows: readonly ChatRow[]) => Promise<void>;
  clear: (rows: readonly ChatRow[]) => Promise<void>;
  threadsOf: (rows: readonly ChatRow[]) => Promise<string[]>;
  failed: (error: unknown) => void;
  /** The newest message of each thread still in this device's outbox. */
  outgoing: ReadonlyMap<string, OutgoingIntent>;
  /** How many messages wait in this device's outbox (the network strip's count). */
  queued: number;
};
const Context = createContext<Lists | null>(null);

export function ListsProvider({ children }: { children: ReactNode }) {
  const data = useShellData();
  const toast = useToast();
  const { owner, server, t, errorText } = useSession();
  const ownerId = owner?.id ?? "";
  const [version, setVersion] = useState(0);
  useEffect(() => subscribeOutgoing(() => setVersion((value) => value + 1)), []);
  // Restored intents show as failed (Q6): they never leave by themselves after a restart.
  useEffect(() => {
    if (!ownerId) return;
    for (const entry of data.inbox)
      void hydrateOutgoing(outgoingKey(server, ownerId, entry.thread_id));
  }, [data.inbox, server, ownerId]);
  const latest = useCallback(
    (thread: string) => outgoingMessages(outgoingKey(server, ownerId, thread)).at(-1)?.message.created_at,
    [server, ownerId],
  );
  // biome-ignore lint/correctness/useExhaustiveDependencies: `version` re-reads the outbox
  const rows = useMemo(
    () => chatRows(data.agents, data.groups, data.inbox, latest),
    [data.agents, data.groups, data.inbox, latest, version],
  );
  // biome-ignore lint/correctness/useExhaustiveDependencies: `version` re-reads the outbox
  const { outgoing, queued } = useMemo(() => {
    const map = new Map<string, OutgoingIntent>();
    let count = 0;
    for (const row of rows) {
      if (!row.threadId) continue;
      const pending = outgoingMessages(outgoingKey(server, ownerId, row.threadId));
      count += pending.length;
      const last = pending.at(-1);
      if (last) map.set(row.threadId, last);
    }
    return { outgoing: map, queued: count };
  }, [rows, server, ownerId, version]);
  const [filter, setFilter] = useState<ListFilter>("all");
  const [selected, setSelected] = useState<ReadonlySet<string> | null>(null);
  const end = useCallback(() => setSelected(null), []);
  useEffect(() => {
    if (!selected) return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      setSelected(null);
      return true;
    });
    return () => sub.remove();
  }, [selected]);
  // A list deleted elsewhere is no longer a filter.
  useEffect(() => {
    if (filter.startsWith("list:") && data.loaded && !data.chatLists.some((list) => `list:${list.id}` === filter))
      setFilter("all");
  }, [filter, data.chatLists, data.loaded]);
  const start = useCallback((key: string) => setSelected(new Set([key])), []);
  const toggle = useCallback((key: string) => {
    setSelected((current) => {
      if (!current) return current;
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next.size ? next : null;
    });
  }, []);
  const selectAll = useCallback((keys: readonly string[]) => {
    setSelected((current) => (current ? new Set([...current, ...keys]) : current));
  }, []);
  const picked = useMemo(() => (selected ? rows.filter((row) => selected.has(row.key)) : []), [rows, selected]);
  const { patchInbox, refresh } = data;
  const merge = useCallback(
    (prefs: ThreadPrefs[], created: boolean) => {
      patchInbox(prefs);
      if (created) void refresh();
    },
    [patchInbox, refresh],
  );
  const threadsOf = useCallback(async (targets: readonly ChatRow[]) => {
    const ids = await Promise.all(targets.map(ensureThread));
    return ids.filter((id): id is string => Boolean(id));
  }, []);
  const prefs = useCallback<Lists["prefs"]>(
    async (targets, change) => {
      if (!targets.length) return;
      const ids = await threadsOf(targets);
      if (!ids.length) return;
      merge(await listsApi.prefs(ids, change), targets.some((row) => !row.threadId || !row.entry));
    },
    [threadsOf, merge],
  );
  const read = useCallback<Lists["read"]>(
    async (targets) => {
      const results = await Promise.all(
        targets
          .filter((row) => row.entry)
          .map((row) =>
            listsApi.read(
              row.entry?.thread_id ?? "",
              Math.max(row.entry?.last_message?.seq ?? 0, row.entry?.last_read_seq ?? 0),
            ),
          ),
      );
      merge(results, false);
    },
    [merge],
  );
  const clear = useCallback<Lists["clear"]>(
    async (targets) => {
      const results = await Promise.all(
        targets.filter((row) => row.threadId).map((row) => listsApi.clear(row.threadId ?? "")),
      );
      merge(results, targets.some((row) => !row.entry));
    },
    [merge],
  );
  const failed = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.code === "thread_pin_limit") toast(t("sh_pin3"));
      else toast(errorText(error), { type: "error" });
    },
    [toast, t, errorText],
  );
  const value = useMemo<Lists>(
    () => ({ rows, filter, setFilter, selected, picked, start, toggle, selectAll, end, prefs, read, clear, threadsOf, failed, outgoing, queued }),
    [rows, filter, selected, picked, start, toggle, selectAll, end, prefs, read, clear, threadsOf, failed, outgoing, queued],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useLists() {
  const value = useContext(Context);
  if (!value) throw new Error("lists_context_missing");
  return value;
}
