import type { Agent, TradeApproval } from "@lonora/contracts";
import { usePathname } from "expo-router";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { AppState, Platform } from "react-native";
import { ApiError, api } from "./api";
import { useSession } from "./session";
import { registerSessionTeardown } from "./session-lifecycle";
import { createVoiceDevice } from "./voice-device";
import { MobileVoiceJoin } from "./voice-transport";
import type { VoiceActivity } from "./voice-types";

type Origin = { agent: Agent; threadId: string; startedAt: number };
type VoiceState = {
  origin: Origin | null;
  connected: boolean;
  minimized: boolean;
  muted: boolean;
  activity: VoiceActivity;
  error: string | null;
  approvals: TradeApproval[];
  start(agent: Agent, threadId: string): Promise<void>;
  end(): Promise<void>;
  toggleMuted(): void;
  minimize(value: boolean): void;
  dismissError(): void;
  updateApproval(value: TradeApproval): void;
};
const Context = createContext<VoiceState | null>(null);
export function useVoiceSession() {
  const value = useContext(Context);
  if (!value) throw new Error("voice_provider_missing");
  return value;
}

export function VoiceSessionProvider({ children }: { children: ReactNode }) {
  const { owner, errorText } = useSession();
  const pathname = usePathname();
  const join = useRef<MobileVoiceJoin | null>(null);
  const [origin, setOrigin] = useState<Origin | null>(null);
  const [connected, setConnected] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [muted, setMuted] = useState(false);
  const [activity, setActivity] = useState<VoiceActivity>({ phase: "listening", level: 0 });
  const [error, setError] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<TradeApproval[]>([]);
  const report = useRef(errorText);
  report.current = errorText;
  const starting = useRef(false);
  const callRequests = useRef(new Set<string>());
  const generation = useRef(0);
  const ownerId = useRef(owner?.id);
  ownerId.current = owner?.id;
  const previousPath = useRef(pathname);

  const end = useCallback(async () => {
    generation.current += 1;
    const current = join.current;
    if (!current) return;
    setOrigin(null);
    setApprovals([]);
    try {
      await current.close();
    } catch (reason) {
      setError(report.current(reason));
    }
  }, []);
  useEffect(() => registerSessionTeardown(end), [end]);
  useEffect(() => {
    if (!owner) void end();
  }, [owner, end]);
  useEffect(() => {
    if (previousPath.current !== pathname && join.current) setMinimized(true);
    previousPath.current = pathname;
  }, [pathname]);
  useEffect(() => {
    const listener = AppState.addEventListener("change", (state) => {
      // No hidden microphone/background service. In-app route changes retain the call.
      if (Platform.OS !== "web" && state === "background") void end();
    });
    return () => {
      listener.remove();
      void end();
    };
  }, [end]);

  useEffect(() => {
    if (!origin || !owner) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const rows = await api.get<TradeApproval[]>(
          `/trading/approvals?thread_id=${encodeURIComponent(origin.threadId)}`,
        );
        if (!disposed) {
          for (const row of rows) if (row.status === "pending") callRequests.current.add(row.id);
          setApprovals((previous) =>
            rows
              .filter(
                (row) =>
                  row.status === "pending" ||
                  Date.parse(row.created_at) >= origin.startedAt ||
                  callRequests.current.has(row.id),
              )
              .map((row) => {
                const old = previous.find((value) => value.id === row.id);
                const rank = { pending: 0, approved: 1, rejected: 1, cancelled: 2, completed: 2 };
                return old &&
                  (rank[old.status] > rank[row.status] || old.results.length > row.results.length)
                  ? old
                  : row;
              }),
          );
        }
      } catch (reason) {
        if (!disposed) setError(report.current(reason));
      }
      if (!disposed) timer = setTimeout(() => void tick(), 2000);
    };
    void tick();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [origin, owner]);

  const start = async (agent: Agent, threadId: string) => {
    if (join.current || starting.current) {
      setMinimized(false);
      return;
    }
    if (!owner) return;
    const capturedGeneration = generation.current;
    const capturedOwner = owner.id;
    starting.current = true;
    setError(null);
    try {
      const status = await api.get<{ transport_configured: boolean }>("/voice/status");
      if (capturedGeneration !== generation.current || capturedOwner !== ownerId.current) return;
      if (!status.transport_configured) throw new ApiError("voice_transport_unconfigured", 409);
      let current: MobileVoiceJoin;
      current = new MobileVoiceJoin(
        setConnected,
        (reason) => setError(report.current(reason)),
        setActivity,
        () => {
          if (join.current === current) {
            join.current = null;
            setOrigin(null);
            setConnected(false);
            setApprovals([]);
          }
        },
        createVoiceDevice(),
        api,
      );
      join.current = current;
      callRequests.current.clear();
      setOrigin({ agent, threadId, startedAt: Date.now() });
      setMinimized(false);
      setMuted(false);
      setApprovals([]);
      await current.connect(agent.id, threadId);
    } catch (reason) {
      setError(report.current(reason));
    } finally {
      starting.current = false;
    }
  };
  return (
    <Context.Provider
      value={{
        origin,
        connected,
        minimized,
        muted,
        activity,
        error,
        approvals,
        start,
        end,
        toggleMuted() {
          const value = !muted;
          join.current?.setMuted(value);
          setMuted(value);
        },
        minimize: setMinimized,
        dismissError() {
          setError(null);
        },
        updateApproval(value) {
          setApprovals((old) => old.map((row) => (row.id === value.id ? value : row)));
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
