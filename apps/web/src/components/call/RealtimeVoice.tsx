import { useEffect, useRef } from "react";
import type { VoiceJoin } from "../../lib/voice";
/** Audio belongs to the call provider, independently of route/overlay presentation. */
export function RealtimeVoice({ session }: { session: VoiceJoin }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    container.current?.appendChild(session.audio);
    return () => {
      session.audio.remove();
    };
  }, [session]);
  return <div ref={container} className="voice-audio-host" aria-hidden="true" />;
}
