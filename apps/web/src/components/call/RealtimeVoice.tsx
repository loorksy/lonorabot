import { Trans } from "@lingui/react/macro";
import { useEffect, useRef } from "react";
import type { VoiceJoin } from "../../lib/voice";

/** Present the click-created native WebRTC audio without renegotiating on React effect replay. */
export function RealtimeVoice({
  session,
  captions,
}: {
  session: VoiceJoin;
  captions: { input: string; output: string };
}) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    container.current?.appendChild(session.audio);
    return () => {
      session.audio.remove();
    };
  }, [session]);
  return (
    <div>
      <div ref={container} />
      {captions.input && (
        <p dir="auto">
          <strong>
            <Trans>You</Trans>:{" "}
          </strong>
          {captions.input}
        </p>
      )}
      {captions.output && (
        <p dir="auto" aria-live="polite">
          <strong>GPT-Live: </strong>
          {captions.output}
        </p>
      )}
    </div>
  );
}
