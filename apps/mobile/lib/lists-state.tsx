// The list's state shared by the chats tab, the archived page and the header: the rows, the
// active filter and the selection. Every change of a conversation's state goes to the server
// and comes back merged (the same contract as Web's lists/state).
import type { Message, ThreadPrefs, ThreadPrefsUpdate } from "@lonora/contracts";
import { type ChatRow, chatRows, type ListFilter } from "@lonora/core";
import { useGlobalSearchParams, usePathname } from "expo-router";
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
import { AppState, BackHandler } from "react-native";
import { useToast } from "../components/shell/toast";
import { ApiError, api } from "./api";
import { waitingSentText } from "./i18n";
import { ensureThread, listsApi } from "./lists-api";
import {
  flushQueued,
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
  const { owner, server, t, errorText, locale } = useSession();
  const ownerId = owner?.id ?? "";
  const [version, setVersion] = useState(0);
  useEffect(() => subscribeOutgoing(() => setVersion((value) => value + 1)), []);
  // Restored intents (Q6): a message the API never answered still waits; one that was in
  // flight when the app went away comes back failed, for the owner's retry.
  useEffect(() => {
    if (!ownerId) return;
    for (const entry of data.inbox)
      void hydrateOutgoing(outgoingKey(server, ownerId, entry.thread_id));
  }, [data.inbox, server, ownerId]);
  const latest = useCallback(
    (thread: string) =>
      outgoingMessages(outgoingKey(server, ownerId, thread)).at(-1)?.message.created_at,
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
      // Only messages still waiting count; a failed one needs the owner's retry (Q6).
      count += pending.filter((item) => item.message.delivery !== "failed").length;
      const last = pending.at(-1);
      if (last) map.set(row.threadId, last);
    }
    return { outgoing: map, queued: count };
  }, [rows, server, ownerId, version]);
  /* Q6, as on Web: while the shell's reads succeed, the messages that waited for the network go
     out by themselves under their own client_nonce, then one toast says how many. Each poll
     (and the poll after the network returns) tries again; a refused one becomes «failed». */
  // biome-ignore lint/correctness/useExhaustiveDependencies: each poll's inbox is the retry tick
  useEffect(() => {
    if (!ownerId || data.offline || !queued) return;
    const keys = rows.flatMap((row) =>
      row.threadId ? [outgoingKey(server, ownerId, row.threadId)] : [],
    );
    void flushQueued(keys, (thread, body) =>
      api
        .post<{ message: Message }>(`/threads/${encodeURIComponent(thread)}/messages`, body)
        .then((accepted) => accepted.message),
    ).then((sent) => {
      if (!sent) return;
      void data.refresh();
      toast(waitingSentText(locale, sent), { type: "success" });
    });
  }, [data.inbox, data.offline, ownerId, server]);
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
    if (
      filter.startsWith("list:") &&
      data.loaded &&
      !data.chatLists.some((list) => `list:${list.id}` === filter)
    )
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
  const picked = useMemo(
    () => (selected ? rows.filter((row) => selected.has(row.key)) : []),
    [rows, selected],
  );
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
  /* The open conversation is read: its unread count and «marked unread» clear on the server (shared
     with Web), and stay clear while new answers arrive in view. The conversation screens need no
     change: the route says which thread is open. */
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ id?: string | string[]; groupId?: string | string[] }>();
  const first = (value?: string | string[]) => (Array.isArray(value) ? value[0] : value);
  const openThread =
    pathname === "/thread"
      ? first(params.id)
      : pathname === "/group-thread"
        ? data.groups.find((group) => group.id === first(params.groupId))?.state?.thread_id
        : undefined;
  const reading = useRef("");
  useEffect(() => {
    const entry = data.inbox.find((row) => row.thread_id === openThread);
    if (!entry || !(entry.unread_count > 0 || entry.marked_unread)) return;
    if (AppState.currentState !== "active") return;
    const seq = Math.max(entry.last_message?.seq ?? 0, entry.last_read_seq);
    const key = `${entry.thread_id}:${seq}:${entry.unread_count}`;
    if (reading.current === key) return;
    reading.current = key;
    void listsApi
      .read(entry.thread_id, seq)
      .then((prefs) => patchInbox([prefs]))
      .catch(() => {
        reading.current = "";
      });
  }, [data.inbox, openThread, patchInbox]);
  const failed = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.code === "thread_pin_limit") toast(t("sh_pin3"));
      else toast(errorText(error), { type: "error" });
    },
    [toast, t, errorText],
  );
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
      outgoing,
      queued,
    }),
    [
      rows,
      filter,
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
      outgoing,
      queued,
    ],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useLists() {
  const value = useContext(Context);
  if (!value) throw new Error("lists_context_missing");
  return value;
}
