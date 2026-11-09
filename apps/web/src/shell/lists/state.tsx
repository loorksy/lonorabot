import { t } from "@lingui/core/macro";
import type { ThreadPrefs, ThreadPrefsUpdate } from "@lonora/contracts";
import { type ChatRow, chatRows, type ListFilter } from "@lonora/core";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useOverlayHistory } from "../../hooks/useOverlayHistory";
import { ApiError } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useToast } from "../Toast";
import { ensureThread, listsApi } from "./api";

/* The list's state shared by the phone list, the desktop pane, the archived page and the
   header: the rows, the active filter, and the selection (a history entry, so Back ends
   it). Every change of a conversation's state goes to the server and comes back merged. */
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
  /** Applies one change to the rows' conversations (created for agents that have none). */
  prefs: (rows: readonly ChatRow[], change: ThreadPrefsUpdate) => Promise<void>;
  read: (rows: readonly ChatRow[]) => Promise<void>;
  clear: (rows: readonly ChatRow[]) => Promise<void>;
  /** The threads of these rows, creating an agent's conversation when it has none. */
  threadsOf: (rows: readonly ChatRow[]) => Promise<string[]>;
  failed: (error: unknown) => void;
};
const Context = createContext<Lists | null>(null);

export function ListsProvider({
  selectable,
  children,
}: {
  /** Phones select on the chat list and the archived page; desktop everywhere. */
  selectable: boolean;
  children: ReactNode;
}) {
  const data = useShellData();
  const toast = useToast();
  const rows = useMemo(
    () => chatRows(data.agents, data.groups, data.inbox),
    [data.agents, data.groups, data.inbox],
  );
  const [filter, setFilterState] = useState<ListFilter>("all");
  const [selected, setSelected] = useState<ReadonlySet<string> | null>(null);
  const end = useCallback(() => setSelected(null), []);
  useOverlayHistory(selected !== null, end);
  useEffect(() => {
    if (!selectable) setSelected(null);
  }, [selectable]);
  // A list that was deleted (here or on mobile) is no longer a filter.
  useEffect(() => {
    if (filter.startsWith("list:") && !data.chatLists.some((list) => `list:${list.id}` === filter))
      setFilterState("all");
  }, [filter, data.chatLists]);
  const pressAt = useRef(0);
  const start = useCallback(
    (key: string) => {
      if (!selectable) return;
      navigator.vibrate?.(12);
      setSelected(new Set([key]));
      pressAt.current = Date.now();
    },
    [selectable],
  );
  const toggle = useCallback((key: string) => {
    setSelected((current) => {
      if (!current) return current;
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      if (!next.size) return null;
      navigator.vibrate?.(6);
      return next;
    });
  }, []);
  const selectAll = useCallback((keys: readonly string[]) => {
    setSelected((current) => (current ? new Set([...current, ...keys]) : current));
  }, []);
  const picked = useMemo(
    () => (selected ? rows.filter((row) => selected.has(row.key)) : []),
    [rows, selected],
  );
  const { patchInbox, refresh } = data;
  const merge = useCallback(
    (prefs: ThreadPrefs[], created: boolean) => {
      patchInbox(prefs);
      // A conversation created for an agent reaches the inbox on the next read.
      if (created) refresh();
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
      merge(
        await listsApi.prefs(ids, change),
        targets.some((row) => !row.threadId || !row.entry),
      );
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
      merge(
        results,
        targets.some((row) => !row.entry),
      );
    },
    [merge],
  );
  const failed = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.code === "thread_pin_limit")
        toast(t`You can pin 3 chats only`);
      else toast(userError(error), { type: "error" });
    },
    [toast],
  );
  const setFilter = useCallback((next: ListFilter) => setFilterState(next), []);
  const value = useMemo<Lists>(
    () => ({
      rows,
      filter,
      setFilter,
      selected,
      picked,
      start,
      toggle,
      selectAll,
      end,
      prefs,
      read,
      clear,
      threadsOf,
      failed,
    }),
    [
      rows,
      filter,
      setFilter,
      selected,
      picked,
      start,
      toggle,
      selectAll,
      end,
      prefs,
      read,
      clear,
      threadsOf,
      failed,
    ],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useLists() {
  const value = useContext(Context);
  if (!value) throw new Error("lists_context_missing");
  return value;
}
