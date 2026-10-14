// Floating call controls adapted from the template, with Lonora's click-owned WebRTC transport.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { AgentAvatar } from "@lonora/ui-web";
import {
  Captions,
  ChevronDown,
  LoaderCircle,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  Play,
  Settings,
  Square,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { useVoice } from "../../hooks/useVoice";
import { userError } from "../../lib/user_error";
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
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!voice.startedAt) return;
    const update = () =>
      setElapsed(Math.floor((Date.now() - (voice.startedAt ?? Date.now())) / 1000));
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [voice.startedAt]);
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
          <button type="button" className="call-name" dir="auto" onClick={onOpenConversation}>
            {name}
          </button>
          {voice.busy && !voice.connected ? (
            <LoaderCircle className="call-connecting" size={20} aria-hidden="true" />
          ) : (
            <CallWaveform meter={voice.meter} />
          )}
          <div className="call-state">
            <VoiceStatus
              connected={voice.connected}
              busy={voice.busy}
              phase={voice.phase}
              muted={voice.muted}
              ending={voice.ending}
            />
            {voice.connected && (
              <span className="call-duration" dir="ltr">
                {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
              </span>
            )}
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
      {voice.playbackBlocked && (
        <button type="button" className="call-playback" onClick={() => void voice.playAudio()}>
          <Play size={14} />
          <Trans>Play audio</Trans>
        </button>
      )}
      {voice.error != null && (
        <div className="call-error" role="alert">
          <p>{userError(voice.error)}</p>
          {!voice.session && !voice.busy && onRetry ? (
            <button type="button" onClick={onRetry}>
              <Phone size={14} />
              <Trans>Retry</Trans>
            </button>
          ) : null}
        </div>
      )}
      <div className="call-secondary">
        <button
          type="button"
          aria-label={t`Conversation transcript`}
          aria-expanded={voice.transcriptOpen}
          onClick={voice.toggleTranscript}
        >
          <Captions size={14} />
          <Trans>Transcript</Trans>
        </button>
        {voice.connected && (
          <button type="button" aria-label={t`Interrupt`} onClick={() => void voice.interrupt()}>
            <Square size={11} />
            <Trans>Interrupt</Trans>
          </button>
        )}
      </div>
      {voice.transcriptOpen && (
        <div className="call-transcript" aria-live="polite">
          {voice.exchanges.length ? (
            voice.exchanges.map((exchange) => (
              <p key={exchange.id} dir="auto">
                <strong>{exchange.channel === "input" ? <Trans>You</Trans> : name}: </strong>
                {exchange.text}
              </p>
            ))
          ) : (
            <p className="muted">
              <Trans>No speech yet</Trans>
            </p>
          )}
        </div>
      )}
    </section>
  );
}
