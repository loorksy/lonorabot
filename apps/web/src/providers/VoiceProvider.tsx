import type { ReactNode } from "react";
import { RealtimeVoice } from "../components/call/RealtimeVoice";
import { useVoiceController, VoiceContext } from "../hooks/useVoice";
export function VoiceProvider({ ownerId, children }: { ownerId: string; children: ReactNode }) {
  const voice = useVoiceController(ownerId);
  return (
    <VoiceContext.Provider value={voice}>
      {children}
      {voice.session ? <RealtimeVoice session={voice.session} /> : null}
    </VoiceContext.Provider>
  );
}
