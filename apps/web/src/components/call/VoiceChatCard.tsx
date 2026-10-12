// Real voice controller for Tampletgrok's call UI boundary. Modified for Lonora; Apache-2.0.
import { lazy, Suspense, useState } from "react";
import { useVoice } from "../../hooks/useVoice";
import type { Message } from "../../lib/api";
import { CallCard } from "./CallCard";
import { VoiceStatus } from "./VoiceStatus";

const RealtimeVoice = lazy(() =>
  import("./RealtimeVoice").then((module) => ({ default: module.RealtimeVoice })),
);

export function VoiceChatCard({
  agentId,
  threadId,
  messages,
}: {
  agentId: string;
  threadId: string;
  messages: Message[];
}) {
  // This controller owns the server session; closing its parent still invokes useVoice teardown.
  const voice = useVoice(agentId, threadId);
  const [transportError, setTransportError] = useState<unknown>();
  async function invoke(action: () => Promise<void>) {
    setTransportError(undefined);
    try {
      await action();
    } catch (error) {
      setTransportError(error);
    }
  }
  return (
    <CallCard
      active={Boolean(voice.session)}
      connected={voice.connected}
      busy={voice.busy}
      messages={messages}
      error={voice.error ?? transportError}
      onStart={() => {
        void invoke(voice.start);
      }}
      onInterrupt={() => {
        void invoke(voice.interrupt);
      }}
      onEnd={() => {
        void invoke(voice.stop);
      }}
      transport={
        voice.session && (
          <Suspense fallback={<VoiceStatus connected={false} busy={true} />}>
            <RealtimeVoice session={voice.session} captions={voice.captions} />
          </Suspense>
        )
      }
    />
  );
}
