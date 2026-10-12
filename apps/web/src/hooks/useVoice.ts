import { useEffect, useRef, useState } from "react";
import { type VoiceFragment, VoiceJoin } from "../lib/voice";

export function useVoice(agentId: string, threadId: string) {
  const [session, setSession] = useState<VoiceJoin | null>(null);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [captions, setCaptions] = useState<{ input: string; output: string }>({
    input: "",
    output: "",
  });
  const current = useRef<VoiceJoin | null>(null);
  const mounted = useRef<string | null>(null);
  const entity = `${agentId}:${threadId}`;
  useEffect(() => {
    mounted.current = entity;
    if (current.current && current.current.entity !== entity) {
      void current.current.close().catch(() => undefined);
      current.current = null;
      setSession(null);
    }
    return () => {
      mounted.current = null;
      const transport = current.current;
      queueMicrotask(() => {
        if (mounted.current !== entity) void transport?.close().catch(() => undefined);
      });
    };
  }, [entity]);
  return {
    session,
    error,
    busy,
    connected,
    captions,
    start: async () => {
      if (current.current) return;
      setBusy(true);
      setError(undefined);
      setCaptions({ input: "", output: "" });
      let transport: VoiceJoin;
      try {
        transport = new VoiceJoin(
          entity,
          (value) => {
            if (current.current === transport) setConnected(value);
          },
          (failure) => {
            if (current.current === transport) setError(failure);
          },
          (channel: "input" | "output", fragment: VoiceFragment) => {
            if (current.current === transport)
              setCaptions((previous) => ({
                ...previous,
                [channel]: (previous[channel] + fragment.delta).slice(-8000),
              }));
          },
          () => {
            if (current.current === transport) {
              current.current = null;
              setSession(null);
              setBusy(false);
            }
          },
        );
        current.current = transport;
        setSession(transport);
        await transport.connect(agentId, threadId);
      } catch (failure) {
        if (mounted.current === entity) setError(failure);
      } finally {
        if (mounted.current === entity) setBusy(false);
      }
    },
    stop: async () => {
      await current.current?.close();
    },
    interrupt: async () => {
      await current.current?.interrupt();
    },
  };
}
