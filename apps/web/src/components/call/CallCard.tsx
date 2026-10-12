// Lonora's real call presentation follows Tampletgrok's CallCard boundary; Apache-2.0.
import { Trans } from "@lingui/react/macro";
import { Mic, PhoneOff, Square } from "lucide-react";
import type { ReactNode } from "react";
import type { Message } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { Transcript } from "./Transcript";
import { VoiceStatus } from "./VoiceStatus";

/** Call controls and transcript for a real server voice session supplied by its controller. */
export function CallCard({
  active,
  connected,
  busy,
  messages,
  error,
  transport,
  onStart,
  onInterrupt,
  onEnd,
}: {
  active: boolean;
  connected: boolean;
  busy: boolean;
  messages: Message[];
  error: unknown;
  transport?: ReactNode;
  onStart: () => void;
  onInterrupt: () => void;
  onEnd: () => void;
}) {
  return (
    <section className="voice-card">
      {active ? (
        <>
          <VoiceStatus connected={connected} busy={!connected} />
          <button type="button" onClick={onInterrupt}>
            <Square size={12} aria-hidden="true" />
            <Trans>Interrupt</Trans>
          </button>
          <button type="button" onClick={onEnd}>
            <PhoneOff size={14} aria-hidden="true" />
            <Trans>End call</Trans>
          </button>
          {transport}
          <Transcript messages={messages} />
        </>
      ) : (
        <button type="button" disabled={busy} onClick={onStart}>
          <Mic size={14} aria-hidden="true" />
          <Trans>Start voice conversation</Trans>
        </button>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
