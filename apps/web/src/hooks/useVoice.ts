import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { Agent, Thread } from "../lib/api";
import { ApiError, api } from "../lib/api";
import { type VoiceFragment, VoiceJoin, voiceSnapshot } from "../lib/voice";
import { useClient } from "../providers/ClientProvider";
export type CallTarget = {
  agentId: string;
  threadId: string;
  name: string;
  color: string;
  avatar: string;
};
export type VoiceExchange = { id: string; channel: "input" | "output"; text: string };
export class VoiceMeter {
  private values = Array<number>(24).fill(0);
  private watchers = new Set<() => void>();
  snapshot = () => this.values;
  subscribe = (watcher: () => void) => {
    this.watchers.add(watcher);
    return () => {
      this.watchers.delete(watcher);
    };
  };
  publish(level: number) {
    this.values = [...this.values.slice(1), Math.max(0, Math.min(1, level))];
    this.watchers.forEach((watcher) => {
      watcher();
    });
  }
  clear() {
    this.values = Array<number>(24).fill(0);
    this.watchers.forEach((watcher) => {
      watcher();
    });
  }
}
export function useVoiceLevels(meter: VoiceMeter) {
  return useSyncExternalStore(meter.subscribe, meter.snapshot, meter.snapshot);
}
type CallState = {
  target: CallTarget | null;
  session: VoiceJoin | null;
  connected: boolean;
  busy: boolean;
  ending: boolean;
  muted: boolean;
  minimized: boolean;
  transcriptOpen: boolean;
  playbackBlocked: boolean;
  phase: "listening" | "speaking";
  startedAt: number | null;
  exchanges: VoiceExchange[];
  error: unknown;
};
const initial: CallState = {
  target: null,
  session: null,
  connected: false,
  busy: false,
  ending: false,
  muted: false,
  minimized: false,
  transcriptOpen: false,
  playbackBlocked: false,
  phase: "listening",
  startedAt: null,
  exchanges: [],
  error: null,
};

export function useVoiceController(ownerId: string) {
  const { events } = useClient();
  const [state, setState] = useState<CallState>(initial);
  const current = useRef<VoiceJoin | null>(null);
  const mounted = useRef<string | null>(null);
  const epoch = useRef(0);
  const pending = useRef(false);
  const fragments = useRef(
    new Map<string, { channel: "input" | "output"; fragment: VoiceFragment }>(),
  );
  const meter = useMemo(() => new VoiceMeter(), []);
  const publish = useCallback((channel: "input" | "output", fragment: VoiceFragment) => {
    if (
      !fragment.event_id ||
      typeof fragment.delta !== "string" ||
      !Number.isFinite(fragment.start_ms) ||
      !Number.isFinite(fragment.end_ms)
    )
      return;
    const key = `${channel}:${fragment.event_id}`;
    if (fragments.current.has(key)) return;
    fragments.current.set(key, { channel, fragment });
    if (fragments.current.size > 2048)
      fragments.current.delete(fragments.current.keys().next().value ?? "");
    const exchanges: VoiceExchange[] = [];
    const ordered = [...fragments.current.values()].sort(
      (a, b) => a.fragment.start_ms - b.fragment.start_ms || a.fragment.end_ms - b.fragment.end_ms,
    );
    for (const item of ordered) {
      const last = exchanges.at(-1);
      if (last?.channel === item.channel)
        last.text = (last.text + item.fragment.delta).slice(-8000);
      else
        exchanges.push({
          id: `${item.channel}:${item.fragment.event_id}`,
          channel: item.channel,
          text: item.fragment.delta,
        });
    }
    setState((previous) => ({ ...previous, exchanges: exchanges.slice(-16) }));
  }, []);

  useEffect(() => {
    mounted.current = ownerId;
    const release = () => {
      const transport = current.current;
      current.current = null;
      epoch.current += 1;
      pending.current = false;
      fragments.current.clear();
      meter.clear();
      setState(initial);
      void transport?.close().catch(() => undefined);
    };
    window.addEventListener("pagehide", release);
    window.addEventListener("lonora:session-expired", release);
    return () => {
      mounted.current = null;
      window.removeEventListener("pagehide", release);
      window.removeEventListener("lonora:session-expired", release);
      const transport = current.current;
      queueMicrotask(() => {
        if (mounted.current !== ownerId) {
          epoch.current += 1;
          void transport?.close().catch(() => undefined);
        }
      });
    };
  }, [ownerId, meter]);

  useEffect(() => {
    const transport = state.session;
    if (!transport) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (transport.session_id) {
        try {
          const snapshot = await voiceSnapshot(transport.session_id);
          if (!live || current.current !== transport) return;
          snapshot.input.forEach((fragment) => {
            publish("input", fragment);
          });
          snapshot.output.forEach((fragment) => {
            publish("output", fragment);
          });
          if (snapshot.status === "connected")
            setState((previous) =>
              previous.connected
                ? previous
                : { ...previous, connected: true, startedAt: previous.startedAt ?? Date.now() },
            );
          if (["closing", "closed", "failed"].includes(snapshot.status)) {
            if (snapshot.error)
              setState((previous) => ({
                ...previous,
                error: new ApiError(snapshot.error ?? "voice_connection_failed", 502),
              }));
            await transport.close();
            return;
          }
        } catch (error) {
          if (live && current.current === transport)
            setState((previous) => ({ ...previous, error }));
        }
      }
      if (live && current.current === transport) timer = setTimeout(() => void tick(), 2000);
    };
    void tick();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [state.session, publish]);

  useEffect(() => {
    const sessionId = current.current?.session_id;
    if (!sessionId) return;
    for (const event of events) {
      if (event.kind !== "voice.transcript" || event.payload.session_id !== sessionId) continue;
      const channel = event.payload.channel;
      if (channel === "input" || channel === "output")
        publish(channel, event.payload as unknown as VoiceFragment);
    }
  }, [events, publish]);

  const start = async (agent: Agent, historicalThread?: string | null) => {
    if (current.current || pending.current) {
      setState((previous) => ({ ...previous, minimized: false }));
      return;
    }
    pending.current = true;
    const generation = ++epoch.current;
    const live = () => mounted.current === ownerId && epoch.current === generation;
    fragments.current.clear();
    meter.clear();
    setState({
      ...initial,
      target: {
        agentId: agent.id,
        threadId: historicalThread ?? "",
        name: agent.name,
        color: agent.color,
        avatar: agent.avatar,
      },
      busy: true,
    });
    try {
      const [thread, readiness] = await Promise.all([
        historicalThread
          ? api.get<Thread>(`/threads/${encodeURIComponent(historicalThread)}`)
          : api.post<Thread>(`/agents/${encodeURIComponent(agent.id)}/conversation`, {}),
        api.get<{ transport_configured: boolean }>("/voice/status"),
      ]);
      if (!live()) return;
      if (thread.agent_id !== agent.id || thread.group_id)
        throw new ApiError("voice_agent_thread_mismatch", 409);
      if (!readiness.transport_configured)
        throw new ApiError("voice_transport_not_configured", 409);
      let transport: VoiceJoin;
      transport = new VoiceJoin(
        `${agent.id}:${thread.id}`,
        (connected) => {
          if (live() && current.current === transport)
            setState((previous) => ({
              ...previous,
              connected,
              startedAt: connected ? (previous.startedAt ?? Date.now()) : previous.startedAt,
            }));
        },
        (error) => {
          if (live() && current.current === transport)
            setState((previous) => ({ ...previous, error }));
        },
        (channel, fragment) => {
          if (live() && current.current === transport) publish(channel, fragment);
        },
        () => {
          if (current.current !== transport) return;
          current.current = null;
          if (live())
            setState((previous) => ({
              ...previous,
              session: null,
              connected: false,
              busy: false,
              ending: false,
              target: previous.error ? previous.target : null,
            }));
        },
        ({ phase, level }) => {
          if (!live() || current.current !== transport) return;
          meter.publish(level);
          setState((previous) => (previous.phase === phase ? previous : { ...previous, phase }));
        },
        (playbackBlocked) => {
          if (live() && current.current === transport)
            setState((previous) => ({ ...previous, playbackBlocked }));
        },
      );
      current.current = transport;
      setState((previous) => ({
        ...previous,
        session: transport,
        startedAt: null,
        target: {
          agentId: agent.id,
          threadId: thread.id,
          name: agent.name,
          color: agent.color,
          avatar: agent.avatar,
        },
      }));
      await transport.connect(agent.id, thread.id);
    } catch (error) {
      if (live()) setState((previous) => ({ ...previous, error }));
    } finally {
      if (epoch.current === generation) pending.current = false;
      if (live()) setState((previous) => ({ ...previous, busy: false }));
    }
  };
  const stop = async () => {
    const transport = current.current;
    pending.current = false;
    if (!transport) {
      epoch.current += 1;
      setState(initial);
      return;
    }
    setState((previous) => ({ ...previous, ending: true, busy: true }));
    try {
      await transport.close();
    } finally {
      if (!current.current || current.current === transport) {
        current.current = null;
        epoch.current += 1;
        fragments.current.clear();
        meter.clear();
        setState(initial);
      }
    }
  };
  return {
    ...state,
    meter,
    start,
    stop,
    expand: () => setState((previous) => ({ ...previous, minimized: false })),
    minimize: () => setState((previous) => ({ ...previous, minimized: true })),
    toggleTranscript: () =>
      setState((previous) => ({ ...previous, transcriptOpen: !previous.transcriptOpen })),
    toggleMute: () => {
      const transport = current.current;
      if (!transport) return;
      transport.setMuted(!transport.muted);
      setState((previous) => ({ ...previous, muted: transport.muted }));
    },
    playAudio: async () => {
      try {
        await current.current?.resumePlayback();
      } catch (error) {
        setState((previous) => ({ ...previous, error }));
      }
    },
    interrupt: async () => {
      try {
        await current.current?.interrupt();
      } catch (error) {
        setState((previous) => ({ ...previous, error }));
      }
    },
  };
}
export const VoiceContext = createContext<ReturnType<typeof useVoiceController> | null>(null);
export function useVoice() {
  const voice = useContext(VoiceContext);
  if (!voice) throw new Error("voice_context_missing");
  return voice;
}
