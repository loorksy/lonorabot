// Floating call controls adapted from the template, with Lonora's click-owned WebRTC transport.
import { t } from "@lingui/core/macro";
import { AgentAvatar } from "@lonora/ui-web";
import {
  ChevronDown,
  LoaderCircle,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  Play,
  Settings,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useVoice } from "../../hooks/useVoice";
import { userError } from "../../lib/user_error";
import { TradeApprovals } from "../trading/TradeApprovals";
import { CallWaveform } from "./CallWaveform";
import { VoiceStatus } from "./VoiceStatus";
import "./call.css";

export function CallCard({
  onSettings,
  onOpenConversation,
  onRetry,
}: {
  onSettings: () => void;
  onOpenConversation: () => void;
  onRetry?: () => void;
}) {
  const voice = useVoice();
  if (!voice.target || voice.minimized) return null;
  const { name, avatar, color } = voice.target;
  return (
    <section
      className="call-overlay"
      aria-label={t`Call with ${name}`}
      data-testid="call-view"
      style={{ "--call-color": color } as CSSProperties}
    >
      <div className="call-pill">
        <button
          type="button"
          className="call-avatar"
          aria-label={t`Open conversation with ${name}`}
          title={name}
          onClick={onOpenConversation}
        >
          <AgentAvatar
            name={name}
            shape={avatar}
            color={color}
            working={voice.phase === "speaking" && voice.connected}
          />
        </button>
        <div className="call-center">
          {voice.busy && !voice.connected ? (
            <LoaderCircle className="call-connecting" size={20} aria-hidden="true" />
          ) : (
            <CallWaveform meter={voice.meter} />
          )}
          <div className="call-accessible-status">
            <VoiceStatus
              connected={voice.connected}
              busy={voice.busy}
              phase={voice.phase}
              muted={voice.muted}
              ending={voice.ending}
            />
          </div>
        </div>
        <button
          type="button"
          className="call-control"
          aria-label={t`Voice settings`}
          title={t`Voice settings`}
          onClick={onSettings}
        >
          <Settings size={19} />
        </button>
        <button
          type="button"
          className="call-control"
          aria-label={voice.muted ? t`Unmute microphone` : t`Mute microphone`}
          title={voice.muted ? t`Unmute microphone` : t`Mute microphone`}
          aria-pressed={voice.muted}
          disabled={!voice.session || voice.ending}
          onClick={voice.toggleMute}
        >
          {voice.muted ? <MicOff size={19} /> : <Mic size={19} />}
        </button>
        <button
          type="button"
          className="call-control end"
          aria-label={t`End call`}
          title={t`End call`}
          disabled={voice.ending}
          onClick={() => {
            void voice.stop().catch(() => undefined);
          }}
        >
          <PhoneOff size={20} />
        </button>
      </div>
      <button
        type="button"
        className="call-minimize"
        aria-label={t`Minimize call`}
        title={t`Minimize call`}
        onClick={voice.minimize}
      >
        <span aria-hidden="true" />
        <ChevronDown size={12} />
      </button>
      <div className="call-approvals">
        <TradeApprovals
          key={voice.target.threadId}
          threadId={voice.target.threadId}
          since={voice.startedAt ?? Date.now()}
        />
      </div>
      {voice.playbackBlocked && (
        <button
          type="button"
          className="call-playback"
          aria-label={t`Play audio`}
          title={t`Play audio`}
          onClick={() => void voice.playAudio()}
        >
          <Play size={14} />
        </button>
      )}
      {voice.error != null && (
        <div className="call-error" role="alert">
          <p>{userError(voice.error)}</p>
          {!voice.session && !voice.busy && onRetry ? (
            <button type="button" aria-label={t`Retry`} title={t`Retry`} onClick={onRetry}>
              <Phone size={14} />
            </button>
          ) : null}
        </div>
      )}
    </section>
  );
}
