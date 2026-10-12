import { Trans } from "@lingui/react/macro";
import { lazy, Suspense, useCallback, useState } from "react";
import { useVoice } from "../../hooks/useVoice";
import type { Message } from "../../lib/api";
import { userError } from "../../lib/user_error";

const RealtimeVoice = lazy(() =>
  import("./RealtimeVoice").then((module) => ({ default: module.RealtimeVoice })),
);

import { Transcript } from "./Transcript";
import { VoiceStatus } from "./VoiceStatus";
export function VoiceChatCard({
  agentId,
  threadId,
  messages,
}: {
  agentId: string;
  threadId: string;
  messages: Message[];
}) {
  const voice = useVoice(agentId, threadId);
  const [connected, setConnected] = useState(false);
  const [transportError, setTransportError] = useState<unknown>();
  const onError = useCallback((e: unknown) => setTransportError(e), []);
  return (
    <section className="voice-card">
      {voice.session ? (
        <>
          <VoiceStatus connected={connected} busy={!connected} />
          <button type="button" onClick={() => void voice.interrupt()}>
            <Trans>Interrupt</Trans>
          </button>
          <button type="button" onClick={() => void voice.stop()}>
            <Trans>End call</Trans>
          </button>
          <Suspense fallback={<VoiceStatus connected={false} busy={true} />}>
            <RealtimeVoice session={voice.session} onStatus={setConnected} onError={onError} />
          </Suspense>
          <Transcript messages={messages} />
        </>
      ) : (
        <button type="button" disabled={voice.busy} onClick={() => void voice.start()}>
          <Trans>Start voice conversation</Trans>
        </button>
      )}
      {(voice.error ?? transportError) != null && (
        <p role="alert">{userError(voice.error ?? transportError)}</p>
      )}
    </section>
  );
}
