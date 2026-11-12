// What the shell fetched once for every screen: agents, groups, the inbox projection, the
// owner's lists and thread settings, runs and attention. Polled every 5 s while the app is active.
import type {
  Agent,
  AttentionNotification,
  ChatList,
  Group,
  InboxEntry,
  Run,
  ThreadPrefs,
  ThreadSettings,
} from "@lonora/contracts";
import { activeStatuses, appOpenReporter, mergePrefs } from "@lonora/core";
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
import { AppState, Platform } from "react-native";
import { api } from "./api";
import { conversationCache, type InboxSnapshot } from "./conversation-cache";
import { useSession } from "./session";

// The owner opened the app: the morning brief's time is learned from it (VISION 11.1).
const reportAppOpen = appOpenReporter((body) => api.post("/app-opens", body));

export type ShellData = {
  agents: Agent[];
  groups: Group[];
  inbox: InboxEntry[];
  chatLists: ChatList[];
  threadSettings: ThreadSettings | null;
  runs: Run[];
  attention: AttentionNotification[];
  busyIds: Set<string>;
  /** False until the first inbox read of this owner landed. */
  loaded: boolean;
  /** The last read failed (the network strip says so). */
  offline: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  patchInbox: (prefs: ThreadPrefs[]) => void;
  setChatLists: (update: (lists: ChatList[]) => ChatList[]) => void;
  setThreadSettings: (settings: ThreadSettings) => void;
  clearAttention: (id: string) => void;
};
const Context = createContext<ShellData | null>(null);

export function ShellDataProvider({ children }: { children: ReactNode }) {
  const { ready, owner, server, errorText } = useSession();
  const scope = useMemo(
    () => (owner ? conversationCache.activate(server, owner.id) : null),
    [server, owner],
  );
  const reportError = useRef(errorText);
  reportError.current = errorText;
  const currentOwner = useRef(owner?.id);
  currentOwner.current = owner?.id;
  const [loadedOwner, setLoadedOwner] = useState<string>();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [inbox, setInbox] = useState<InboxEntry[]>([]);
  const [chatLists, setChatListsState] = useState<ChatList[]>([]);
  const [threadSettings, setThreadSettingsState] = useState<ThreadSettings | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [attention, setAttention] = useState<AttentionNotification[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  // Local confirmed writes bump this; a primary read that started before the last one is dropped.
  const writes = useRef(0);

  useEffect(() => {
    const cached = conversationCache.get<InboxSnapshot>(scope, "inbox");
    setInbox(cached?.inbox ?? []);
    setAgents(cached?.agents ?? []);
    setGroups(cached?.groups ?? []);
    setRuns(cached?.runs ?? []);
    setAttention(cached?.attention ?? []);
    setChatListsState([]);
    setThreadSettingsState(null);
    setLoadedOwner(cached ? currentOwner.current : undefined);
  }, [scope]);

  const refresh = useCallback(
    async (stillLive: () => boolean = () => true) => {
      const requestOwner = currentOwner.current;
      const startedAt = writes.current;
      const current = () =>
        stillLive() && requestOwner === currentOwner.current && conversationCache.current(scope);
      try {
        const previous = conversationCache.get<InboxSnapshot>(scope, "inbox");
        let extras = { runs: previous?.runs ?? [], attention: previous?.attention ?? [] };
        const primary = Promise.all([
          api.get<Agent[]>("/agents"),
          api.get<Group[]>("/groups"),
          api.get<InboxEntry[]>("/threads/inbox"),
          api.get<ChatList[]>("/chat-lists").catch(() => null),
          api.get<ThreadSettings>("/threads/settings").catch(() => null),
        ]).then(([nextAgents, nextGroups, nextInbox, nextLists, nextSettings]) => {
          if (!current() || writes.current !== startedAt) return;
          conversationCache.set(scope, "inbox", {
            agents: nextAgents,
            groups: nextGroups,
            inbox: nextInbox,
            ...extras,
          });
          setLoadedOwner(requestOwner);
          setInbox(nextInbox);
          setAgents(nextAgents);
          setGroups(nextGroups);
          if (nextLists) setChatListsState(nextLists);
          if (nextSettings) setThreadSettingsState(nextSettings);
          setError(null);
          setOffline(false);
        });
        const auxiliary = Promise.all([
          api.get<Run[]>("/runs"),
          api.get<AttentionNotification[]>("/attention"),
        ]).then(([nextRuns, nextAttention]) => {
          if (!current()) return;
          extras = { runs: nextRuns, attention: nextAttention };
          const cached = conversationCache.get<InboxSnapshot>(scope, "inbox");
          if (cached) conversationCache.set(scope, "inbox", { ...cached, ...extras });
          setRuns(nextRuns);
          setAttention(nextAttention);
        });
        await Promise.all([primary, auxiliary]);
      } catch (reason) {
        if (stillLive() && requestOwner === currentOwner.current) {
          setError(reportError.current(reason));
          // A read that fails without an HTTP answer is the network; an answer is the server.
          setOffline(
            !(
              reason &&
              typeof reason === "object" &&
              "status" in reason &&
              (reason as { status: number }).status > 0
            ),
          );
        }
      }
    },
    [scope],
  );

  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useEffect(() => {
    if (!ready || !owner) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let running = false;
    const tick = async () => {
      if (running || disposed) return;
      running = true;
      try {
        if (AppState.currentState === "active") await refreshRef.current(() => !disposed);
      } finally {
        running = false;
        if (!disposed) timer = setTimeout(() => void tick(), 5000);
      }
    };
    reportAppOpen();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") reportAppOpen();
      if (state === "active" && !disposed) {
        clearTimeout(timer);
        void tick();
      }
    });
    const online = () => {
      clearTimeout(timer);
      void tick();
    };
    if (Platform.OS === "web" && typeof window !== "undefined")
      window.addEventListener("online", online);
    void tick();
    return () => {
      subscription.remove();
      if (Platform.OS === "web" && typeof window !== "undefined")
        window.removeEventListener("online", online);
      disposed = true;
      clearTimeout(timer);
    };
  }, [ready, owner]);

  const patchInbox = useCallback(
    (prefs: ThreadPrefs[]) => {
      writes.current += 1;
      setInbox((entries) => {
        const next = mergePrefs(entries, prefs);
        const cached = conversationCache.get<InboxSnapshot>(scope, "inbox");
        if (cached) conversationCache.set(scope, "inbox", { ...cached, inbox: next });
        return next;
      });
    },
    [scope],
  );
  const setChatLists = useCallback((update: (lists: ChatList[]) => ChatList[]) => {
    writes.current += 1;
    setChatListsState(update);
  }, []);
  const setThreadSettings = useCallback((settings: ThreadSettings) => {
    writes.current += 1;
    setThreadSettingsState(settings);
  }, []);
  const clearAttention = useCallback(
    (id: string) => setAttention((rows) => rows.filter((row) => row.id !== id)),
    [],
  );
  const busyIds = useMemo(
    () =>
      new Set(runs.filter((run) => activeStatuses.includes(run.status)).map((run) => run.agent_id)),
    [runs],
  );
  const value = useMemo<ShellData>(
    () => ({
      agents,
      groups,
      inbox,
      chatLists,
      threadSettings,
      runs,
      attention,
      busyIds,
      loaded: Boolean(owner) && loadedOwner === owner?.id,
      offline,
      error,
      refresh: () => refreshRef.current(),
      patchInbox,
      setChatLists,
      setThreadSettings,
      clearAttention,
    }),
    [
      agents,
      groups,
      inbox,
      chatLists,
      threadSettings,
      runs,
      attention,
      busyIds,
      owner,
      loadedOwner,
      offline,
      error,
      patchInbox,
      setChatLists,
      setThreadSettings,
      clearAttention,
    ],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useShellData(): ShellData {
  const value = useContext(Context);
  if (!value) throw new Error("shell_data_missing");
  return value;
}
