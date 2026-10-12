import { useEffect, useState } from "react";
import { interruptVoice, startVoice, stopVoice, type VoiceJoin } from "../lib/voice";
export function useVoice(agentId: string, threadId: string) {
  const [session, setSession] = useState<VoiceJoin | null>(null);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  useEffect(
    () => () => {
      if (session) void stopVoice(session.session_id).catch(() => undefined);
    },
    [session],
  );
  return {
    session,
    error,
    busy,
    start: async () => {
      setBusy(true);
      setError(undefined);
      try {
        setSession(await startVoice(agentId, threadId));
      } catch (e) {
        setError(e);
      } finally {
        setBusy(false);
      }
    },
    stop: async () => {
      if (session) await stopVoice(session.session_id);
      setSession(null);
    },
    interrupt: async () => {
      if (session) await interruptVoice(session.session_id);
    },
  };
}
